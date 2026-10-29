from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import ClassVar, Iterator, Optional, Tuple, Union
from urllib.parse import urljoin

# Third Party Imports.
from scrapling.parser import Selector
from scrapling.spiders import Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_software import MarketplaceSoftware


class ArubaCloudMarketplaceCrawler(BaseMarketplaceCrawler):
    """Aruba Cloud marketplace crawler: the cloud apps, one-click virtual machine templates.

    Attributes:
        CARDS (ClassVar[str]): The selector of the application cards of the catalogue.
        AVAILABILITY (ClassVar[re.Pattern[str]]): The availability line of a card (operating systems), not a
            description.
        SLUG_SEPARATORS (ClassVar[re.Pattern[str]]): The characters replaced by a dash in the listing anchors.

    Notes:
        The https://www.arubacloud.com/cloud-apps/ page lists the application catalogue in the `section#catalogo`
        section and the untitled sections following it (the featured cards above it repeat the first ones). Each
        `article.card` gives a name (`h3[data-mh=title]`), a category badge (the `span` of the first paragraph,
        missing for some cards) and a description (the next paragraph), then an availability line (Linux or
        Windows). The few cards with a "Learn more" link get that application page as URL, the others the catalogue
        page with an anchor made of their name. The page gives no publisher. The marketplace taxonomy is flat: the
        category path is the badge text, without identifier.
    """

    CARDS: ClassVar[str] = "section#catalogo article.card, section#catalogo ~ section article.card"
    AVAILABILITY: ClassVar[re.Pattern[str]] = re.compile(r"^availability\b", re.IGNORECASE)
    SLUG_SEPARATORS: ClassVar[re.Pattern[str]] = re.compile(r"[^0-9a-z]+")

    name = "aruba-marketplace"
    catalogue_url: ClassVar[str] = "https://www.arubacloud.com/cloud-apps/"

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

    def _listing_url(self, card: Selector, name: str, page_url: str) -> Optional[str]:
        """Get the URL of a card: its application page, else the catalogue page with an anchor made of its name.

        Args:
            card (Selector): The application card.
            name (str): The application name, e.g. `MinIO`.
            page_url (str): The catalogue page URL.

        Returns:
            Optional[str]: The URL, e.g. `https://www.arubacloud.com/vps/n8n/`, `None` without link nor name.
        """
        href = card.css("a::attr(href)").get()
        if href:
            return urljoin(page_url, href)
        slug = self.SLUG_SEPARATORS.sub("-", self._clean_text(name).casefold()).strip("-")
        if not slug:
            self.logger.debug("The %s card %r has neither link nor name, it has no URL.", self.name, name)
            return None
        self.logger.debug("The %s card %r has no link, it is anchored as %r.", self.name, name, slug)
        return f"{self.catalogue_url}#{slug}"

    def _card_texts(self, card: Selector) -> Tuple[str, str]:
        """Read the category badge and the description of a card.

        Args:
            card (Selector): The application card.

        Returns:
            Tuple[str, str]: The category (empty when the card has none) and the description (empty when missing).
        """
        badge = card.css(".text-neutral-700 p:first-child span").first
        category = self._clean_text(badge.get_all_text(separator=" ", strip=True)) if badge is not None else ""
        description = ""
        for paragraph in card.css(".text-neutral-700 p"):
            text = self._clean_text(paragraph.get_all_text(separator=" ", strip=True))
            if text and text != category and not self.AVAILABILITY.match(text):
                description = text
                break
        return category, description

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the applications of the catalogue page.

        Args:
            response (Response): The catalogue page.

        Yields:
            Iterator[MarketplaceSoftware]: Each valid application.
        """
        cards = response.css(self.CARDS)
        self.logger.debug("%d application cards in the %s page %s.", len(cards), self.name, response.url)
        for card in cards:
            title = card.css("h3[data-mh=title]").first
            if title is None:
                self.logger.debug("Skipping a %s card without name.", self.name)
                continue
            name = title.get_all_text(separator=" ", strip=True)
            category, description = self._card_texts(card)
            software = self._build_software(
                name,
                description,
                self._listing_url(card, name, response.url),
                delivery=DeliveryMethod.VIRTUAL_MACHINE,
                marketplace_categories=[category],
                marketplace_category_paths=[self._category([category])],
            )
            if software is not None:
                yield software
