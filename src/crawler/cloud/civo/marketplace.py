from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Iterator, Optional
from urllib.parse import urljoin

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.marketplace_software import MarketplaceSoftware


class CivoMarketplaceCrawler(BaseMarketplaceCrawler):
    """Civo marketplace crawler.

    Attributes:
        CARD (ClassVar[str]): The selector of the application cards.

    Notes:
        The https://www.civo.com/marketplace page lists every application installed on the Civo Kubernetes clusters
        as a card (`a.marketplace-application`): its name, its description and its category badge. The featured
        applications are shown twice: the duplicates (same page) are skipped.
    """

    CARD: ClassVar[str] = "a.marketplace-application"

    name = "civo-marketplace"
    catalogue_url: ClassVar[str] = "https://www.civo.com/marketplace"

    ############################
    # Internal Helpers Methods #
    ############################

    def _text(self, card: Selector, selector: str) -> Optional[str]:
        """Read the text of the first element of a card matching a selector.

        Args:
            card (Selector): The application card.
            selector (str): The CSS selector.

        Returns:
            Optional[str]: The text, `None` without matching element.
        """
        element = card.css(selector).first
        return element.get_all_text(separator=" ", strip=True) if element is not None else None

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of the application cards.

        Args:
            response (Response): The marketplace page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid software of the page, duplicates included.
        """
        cards = response.css(self.CARD)
        self.logger.info("%d application cards in the %s page %s.", len(cards), self.name, response.url)
        for card in cards:
            link = card.attrib.get("href")
            software = self._build_software(
                self._text(card, "h5"),
                self._text(card, ".description p") or self._text(card, ".description"),
                urljoin(response.url, link) if link else None,
                None,
                DeliveryMethod.KUBERNETES,
                [self._text(card, "span.badge")],
            )
            if software is not None:
                yield software
