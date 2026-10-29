from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import ClassVar, Iterator, Optional, Union

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.combell.enums import CombellBadge, CombellCategorySlug
from crawler.enums import HtmlAttribute
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_software import MarketplaceSoftware


class CombellMarketplaceCrawler(BaseMarketplaceCrawler):
    """Combell marketplace crawler: the content management systems supported by the Combell web hosting.

    Attributes:
        CATEGORY (ClassVar[str]): The marketplace category of every listing, the page lists content management
            systems.
        CATEGORY_ID (ClassVar[CombellCategorySlug]): The identifier of the category, the slug of the page URL.
        ONE_CLICK_DESCRIPTION (ClassVar[str]): The description of the listings marked "One-click install".
        SUPPORTED_DESCRIPTION (ClassVar[str]): The description of the other listings, only said to be supported.
        NAME_SUFFIX (ClassVar[re.Pattern[str]]): The ` hosting` suffix of some card labels, e.g.
            `Umbraco .NET hosting`.
        SLUG_SEPARATORS (ClassVar[re.Pattern[str]]): The characters replaced by a dash in the listing anchors.

    Notes:
        The https://www.combell.com/en/hosting/cms page ("Combell supports any CMS") shows one card per content
        management system (`div.card.shadow`), named only by the `alt` text of its logo. The cards have no
        description and their link leads to a hosting plan, not to an application page: each listing gets a
        generic description and the page URL with an anchor made of its name. A few cards carry a
        "One-click install" badge (installed from the control panel), the others are only said to be supported.
        Every listing is kept as a one-click application of the web hosting. The page gives no publisher. The page
        shows no category element: being the CMS page of the hosting, its category path is `CMS`, identified by the
        `cms` slug of its URL.
    """

    CATEGORY: ClassVar[str] = "CMS"
    CATEGORY_ID: ClassVar[CombellCategorySlug] = CombellCategorySlug.CMS
    ONE_CLICK_DESCRIPTION: ClassVar[str] = "One-click installation on Combell web hosting."
    SUPPORTED_DESCRIPTION: ClassVar[str] = "Supported on Combell web hosting."
    NAME_SUFFIX: ClassVar[re.Pattern[str]] = re.compile(r"\s+hosting$", re.IGNORECASE)
    SLUG_SEPARATORS: ClassVar[re.Pattern[str]] = re.compile(r"[^0-9a-z]+")

    name = "combell-marketplace"
    catalogue_url: ClassVar[str] = "https://www.combell.com/en/hosting/cms"

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
        """Build the URL of a listing: the page with an anchor made of the listing name.

        Args:
            name (str): The listing name, e.g. `CMS Made Simple`.

        Returns:
            Optional[str]: The URL, e.g. `https://www.combell.com/en/hosting/cms#cms-made-simple`, `None` without a
                name.
        """
        slug = self.SLUG_SEPARATORS.sub("-", self._clean_text(name).casefold()).strip("-")
        return f"{self.catalogue_url}#{slug}" if slug else None

    def _is_one_click(self, card: Selector) -> bool:
        """Tell whether a card carries the "One-click install" badge (a sibling of the card).

        Args:
            card (Selector): The card.

        Returns:
            bool: Whether the listing is marked as installed in one click.
        """
        badges = card.xpath("../*[contains(concat(' ', normalize-space(@class), ' '), ' badge ')]")
        return any(
            CombellBadge.ONE_CLICK in badge.get_all_text(separator=" ", strip=True).casefold() for badge in badges
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the content management systems of the page.

        Args:
            response (Response): The page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid content management system.
        """
        cards = response.css("div.card.shadow")
        self.logger.debug("%d cards in the %s page %s.", len(cards), self.name, response.url)
        path = self._category([self.CATEGORY], self.CATEGORY_ID)
        for card in cards:
            logo = card.css(":scope > img").first
            label = self._clean_text(logo.attrib.get(HtmlAttribute.ALT)) if logo is not None else ""
            if not label:
                self.logger.debug("Skipping a %s card without logo label.", self.name)
                continue
            name = self.NAME_SUFFIX.sub("", label)
            description = self.ONE_CLICK_DESCRIPTION if self._is_one_click(card) else self.SUPPORTED_DESCRIPTION
            software = self._build_software(
                name,
                description,
                self._listing_url(name),
                delivery=DeliveryMethod.ONE_CLICK_APP,
                marketplace_categories=[self.CATEGORY],
                marketplace_category_paths=[path],
            )
            if software is not None:
                yield software
