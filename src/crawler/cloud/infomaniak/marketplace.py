from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import ClassVar, Iterator, Optional, Union

# Third Party Imports.
from scrapling.spiders import Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_software import MarketplaceSoftware


class InfomaniakMarketplaceCrawler(BaseMarketplaceCrawler):
    """Infomaniak marketplace crawler: the applications deployed in a few clicks on Jelastic Cloud.

    Attributes:
        TABS (ClassVar[str]): The selector of the tab buttons, each one naming a category.
        PANELS (ClassVar[str]): The selector of the tab panels, in the order of the tabs.
        ITEMS (ClassVar[str]): The selector of the application blocks of a panel.
        NAME (ClassVar[str]): The selector of the application name of a block.
        DESCRIPTION (ClassVar[str]): The selector of the application description of a block (the first one, the
            next ones are feature bullets).
        SLUG_SEPARATORS (ClassVar[re.Pattern[str]]): The characters replaced by a dash in the listing anchors.

    Notes:
        The https://www.infomaniak.com/en/hosting/dedicated-and-cloud-servers/jelastic-cloud/applications page
        (rendered on the server, read over HTTP) shows a curated selection of the Jelastic Cloud marketplace in
        tabs (Web sites, E-commerce, Collaboration, Communication): the tab label is the category of the
        applications of its panel. The class names are CSS modules (`IkTypography-module--h4--7067e`): only their
        stable prefixes are matched, never the hashed suffixes. There is no application page: each listing gets the
        page URL with an anchor made of its name. The page gives no publisher. Some descriptions of the page belong
        to other applications (e.g. Ghost, Drupal and Joomla described as database engines): they are kept as
        published. The marketplace taxonomy is flat: the category path is the tab label, identified by the `id` of
        its tab panel (e.g. `ecommerce`).
    """

    TABS: ClassVar[str] = '[class*="Tabs-module--tabsTab--"] button'
    PANELS: ClassVar[str] = '[class*="FeaturesSection-module--sectionContainerBentosContent--"]'
    ITEMS: ClassVar[str] = '[class*="BentoLayout-module--bentoLayout--"]'
    NAME: ClassVar[str] = 'p[class*="IkTypography-module--h4--"]'
    DESCRIPTION: ClassVar[str] = '[class*="IkTypography-module--body2--"]'
    SLUG_SEPARATORS: ClassVar[re.Pattern[str]] = re.compile(r"[^0-9a-z]+")

    name = "infomaniak-marketplace"
    catalogue_url: ClassVar[str] = (
        "https://www.infomaniak.com/en/hosting/dedicated-and-cloud-servers/jelastic-cloud/applications"
    )

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
            name (str): The listing name, e.g. `Odoo Community Edition`.

        Returns:
            Optional[str]: The URL, e.g. `<page>#odoo-community-edition`, `None` without a name.
        """
        slug = self.SLUG_SEPARATORS.sub("-", self._clean_text(name).casefold()).strip("-")
        return f"{self.catalogue_url}#{slug}" if slug else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the applications of each tab of the page.

        Args:
            response (Response): The applications page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid application, with its tab label as category.

        Raises:
            CatalogueFormatError: If the page has not as many tabs as tab panels.
        """
        tabs = [self._clean_text(tab.get_all_text(separator=" ", strip=True)) for tab in response.css(self.TABS)]
        panels = response.css(self.PANELS)
        self.logger.debug("%d tabs and %d panels in the %s page %s.", len(tabs), len(panels), self.name, response.url)
        if len(tabs) != len(panels):
            self.logger.error(
                "The %s page %s has %d tabs for %d panels.", self.name, response.url, len(tabs), len(panels)
            )
            raise CatalogueFormatError(self.name, response.url, "the tabs do not match the tab panels")
        for tab, panel in zip(tabs, panels, strict=True):
            path = self._category([tab], panel.attrib.get(HtmlAttribute.ID) or None)
            for item in panel.css(self.ITEMS):
                title = item.css(self.NAME).first
                description = item.css(self.DESCRIPTION).first
                if title is None or description is None:
                    self.logger.debug("Skipping a %s block without name or description in the tab %r.", self.name, tab)
                    continue
                name = title.get_all_text(separator=" ", strip=True)
                software = self._build_software(
                    name,
                    description.get_all_text(separator=" ", strip=True),
                    self._listing_url(name),
                    delivery=DeliveryMethod.CONTAINER,
                    marketplace_categories=[tab],
                    marketplace_category_paths=[path],
                )
                if software is not None:
                    yield software
