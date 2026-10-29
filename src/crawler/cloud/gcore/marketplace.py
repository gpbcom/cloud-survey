from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import ClassVar, Iterator, Optional, Union

# Third Party Imports.
from scrapling.spiders import Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_software import MarketplaceSoftware


class GcoreMarketplaceCrawler(BaseMarketplaceCrawler):
    """Gcore marketplace crawler: the application templates of the Gcore cloud virtual machines.

    Attributes:
        SLUG_SEPARATORS (ClassVar[re.Pattern[str]]): The characters replaced by a dash in the listing anchors.

    Notes:
        The https://gcore.com/cloud/marketplace page (Angular, rendered on the server, so read over HTTP) lists the
        applications a virtual machine can be created from (`ul.gc-available-services-list > li`): a name
        (`h3.gc-column-title`) and a description (`p`). There is no application page, the links lead to the sign-up
        form: each listing gets the marketplace page URL with an anchor made of its name. The page gives no
        publisher and no category. The `robots.txt` of the website declares
        `Content-Signal: ai-train=no, search=yes, ai-input=no` and is obeyed.
    """

    SLUG_SEPARATORS: ClassVar[re.Pattern[str]] = re.compile(r"[^0-9a-z]+")

    name = "gcore-marketplace"
    catalogue_url: ClassVar[str] = "https://gcore.com/cloud/marketplace"

    def __init__(
        self,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
        classifier: Optional[SoftwareClassifier] = None,
    ) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
            classifier (Optional[SoftwareClassifier]): The software classifier, the project rules by default.
        """
        super().__init__(crawldir=crawldir, interval=interval, classifier=classifier)

    ############################
    # Internal Helpers Methods #
    ############################

    def _listing_url(self, name: str) -> Optional[str]:
        """Build the URL of a listing: the marketplace page with an anchor made of the listing name.

        Args:
            name (str): The listing name, e.g. `Prometheus`.

        Returns:
            Optional[str]: The URL, e.g. `https://gcore.com/cloud/marketplace#prometheus`, `None` without a name.
        """
        slug = self.SLUG_SEPARATORS.sub("-", self._clean_text(name).casefold()).strip("-")
        return f"{self.catalogue_url}#{slug}" if slug else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the application templates of the marketplace page.

        Args:
            response (Response): The marketplace page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid application template.
        """
        listings = response.css("ul.gc-available-services-list > li")
        self.logger.debug("%d listings in the %s page %s.", len(listings), self.name, response.url)
        for listing in listings:
            title = listing.css("h3.gc-column-title").first
            description = listing.css("p").first
            if title is None or description is None:
                self.logger.debug("Skipping a %s listing without name or description.", self.name)
                continue
            name = title.get_all_text(separator=" ", strip=True)
            software = self._build_software(
                name,
                description.get_all_text(separator=" ", strip=True),
                self._listing_url(name),
                delivery=DeliveryMethod.VIRTUAL_MACHINE,
            )
            if software is not None:
                yield software
