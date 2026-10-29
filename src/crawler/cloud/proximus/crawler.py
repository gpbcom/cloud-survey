from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.proximus.enums import ProximusPageKind
from crawler.enums import HtmlAttribute
from models.cloud.enums import PriceModel
from models.cloud.products.product import CloudProduct


class ProximusNXTCrawler(BaseCloudCrawler):
    """Proximus NXT catalogue crawler.

    Attributes:
        ICT_URL (ClassVar[str]): The ICT page for large companies, listing the ICT categories.
        NETWORKS_URL (ClassVar[str]): The network solutions page for large companies, listing its categories.
        TELEPHONY_URL (ClassVar[str]): The telephony page for large companies, listing its categories.
        NOT_PRODUCT_LINK (ClassVar[re.Pattern[str]]): The card links to rate (price list) pages.
        CARDS (ClassVar[str]): The CSS selector of the page cards (media boxes).
        HEADINGS (ClassVar[str]): The CSS selector of a card heading.
        PAGE_ID (ClassVar[re.Pattern[str]]): The language and page identifier segments of the website paths, e.g.
            `/en/id_cl_privatecloud/`, the `id_catl_` identifiers marking the category pages.
        BREADCRUMB (ClassVar[str]): The CSS selector of the breadcrumb items of a page, but the home one.
        UNPRICED_REASON (ClassVar[Optional[str]]): Why the provider has no public price.
        UNPRICED_MODEL (ClassVar[PriceModel]): How its products are priced (on request).

    Notes:
        The main source is the cards of the cloud solutions page of Proximus NXT (the ICT offer for large companies):
        a card holds a heading, a description and a link. The ICT page completes it with the other ICT categories
        (cybersecurity, data and AI, customer interactions, workplace...), whose pages hold the same cards, and the
        network solutions and telephony pages for large companies complete the whole catalogue the same way. A card
        is a product when its link leads to a product page under the page path (`id_cl_` identifier), a category
        when it leads to a category page under the page path (`id_catl_`), requested in turn. The other cards (news,
        experts, sectors, newsletter, links to other websites) and the rate pages are skipped.
        The catalogue categories of a product are the breadcrumb of the category page listing it, home excluded
        (e.g. `ICT for large companies`, `Cloud solutions for large companies`).
        Proximus NXT publishes no price: in price mode its catalogue page is read as the evidence, and each live
        product is priced on request (a quote).
    """

    ICT_URL: ClassVar[str] = (
        "https://www.proximus.be/en/id_catl_itservices/companies-and-public-sector/ict-for-large-companies.html"
    )
    NETWORKS_URL: ClassVar[str] = (
        "https://www.proximus.be/en/id_catl_networks/companies-and-public-sector/"
        "network-solutions-for-large-companies.html"
    )
    TELEPHONY_URL: ClassVar[str] = (
        "https://www.proximus.be/en/id_catl_telephony/companies-and-public-sector/telephony-for-large-companies.html"
    )
    NOT_PRODUCT_LINK: ClassVar[re.Pattern[str]] = re.compile(r"rates|tariff|pric(e|ing)", re.IGNORECASE)
    CARDS: ClassVar[str] = ".rs-mediabox"
    HEADINGS: ClassVar[str] = "h1, h2, h3, h4, h5, h6"
    PAGE_ID: ClassVar[re.Pattern[str]] = re.compile(r"^/[a-z]{2}/id_([a-z]+)_[^/]*/")
    BREADCRUMB: ClassVar[str] = "ul.breadcrumbs > li:not(.rs-breadcrumb-item-home)"

    UNPRICED_REASON: ClassVar[Optional[str]] = (
        "Proximus NXT publishes no price: its cloud and ICT services are quoted on request (contact sales)."
    )
    UNPRICED_MODEL: ClassVar[PriceModel] = PriceModel.QUOTE

    name = "proximus"
    catalogue_url: ClassVar[str] = (
        "https://www.proximus.be/en/id_catl_itcloud/companies-and-public-sector/ict-for-large-companies/"
        "cloud-solutions.html"
    )
    complement_urls: ClassVar[Tuple[str, ...]] = (ICT_URL, NETWORKS_URL, TELEPHONY_URL)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Proximus NXT ", "Proximus ")

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)

    ############################
    # Internal Helpers Methods #
    ############################

    def _section(self, url: str) -> Tuple[Optional[str], str]:
        """Split a website page into its page kind and its section path.

        Args:
            url (str): The absolute page URL.

        Returns:
            Tuple[Optional[str], str]: The page kind (`catl` for a category, `cl` for a product, `None` for another
                page) and the path after the page identifier, without the `.html` extension, e.g.
                `companies-and-public-sector/ict-for-large-companies/cloud-solutions`.
        """
        path = urlparse(url).path
        match = self.PAGE_ID.match(path)
        if match is None:
            return None, path.removesuffix(".html").strip("/")
        return match.group(1), path[match.end() :].removesuffix(".html").strip("/")

    def _cards(self, response: Response) -> List[Tuple[str, str, str]]:
        """Read the cards of a page leading to a page of its section, the best card of each linked page only.

        Args:
            response (Response): The category page.

        Returns:
            List[Tuple[str, str, str]]: The name, description and absolute link of each card, in the page order.
                When several cards lead to the same page, the one with the highest heading (e.g. the product card
                rather than a news card) is kept.
        """
        host = urlparse(response.url).netloc
        section = f"{self._section(response.url)[1]}/"
        best: Dict[str, Tuple[int, int, Tuple[str, str, str]]] = {}
        for position, card in enumerate(response.css(self.CARDS)):
            heading, text, link = card.css(self.HEADINGS).first, card.css("p").first, card.css("a[href]").first
            if heading is None or text is None or link is None:
                self.logger.debug("Skipping a card of %s, without heading, description or link.", response.url)
                continue
            name = self._clean_text(heading.get_all_text(separator=" ", strip=True))
            description = self._clean_text(text.get_all_text(separator=" ", strip=True))
            url = urljoin(response.url, link.attrib.get(HtmlAttribute.HREF, ""))
            if not (name and description):
                self.logger.debug("Skipping the card %r of %s, without name or description.", name, response.url)
                continue
            if urlparse(url).netloc != host or not self._section(url)[1].startswith(section):
                self.logger.debug("Skipping the card %r (%s), not a page of the section.", name, url)
                continue
            if self.NOT_PRODUCT_LINK.search(urlparse(url).path):
                self.logger.debug("Skipping the card %r (%s), a rate page.", name, url)
                continue
            level = int(str(heading.tag)[1])
            key = self._url_key(url)
            if key not in best or level < best[key][0]:
                best[key] = (level, position, (name, description, url))
        return [card for _, _, card in sorted(best.values(), key=lambda entry: entry[1])]

    def _breadcrumb(self, response: Response) -> List[str]:
        """Read the breadcrumb of a category page, without its home item.

        Args:
            response (Response): The category page.

        Returns:
            List[str]: The breadcrumb labels, the broadest first, e.g. `["ICT for large companies", "Cloud
                solutions for large companies"]`, empty when the page has none.
        """
        labels = [
            self._clean_text(item.get_all_text(separator=" ", strip=True)) for item in response.css(self.BREADCRUMB)
        ]
        self.logger.debug("Breadcrumb of %s: %s.", response.url, labels)
        return [label for label in labels if label]

    def _card_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the cards of a page, skipping the category cards.

        Args:
            response (Response): The category page.

        Yields:
            Iterator[CloudProduct]: Each valid product card, filed under the breadcrumb of the page.
        """
        categories = self._breadcrumb(response)
        for name, description, url in self._cards(response):
            if self._section(url)[0] == ProximusPageKind.CATEGORY:
                self.logger.debug("Skipping the card %r (%s), a category.", name, url)
                continue
            if product := self._build_product(name, description, url, categories=categories):
                yield product

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_products(self, response: Response) -> Iterator[CloudProduct]:
        """Extract the products of the cards of a category page.

        Args:
            response (Response): The category page.

        Returns:
            Iterator[CloudProduct]: The valid products of the page.
        """
        self.logger.debug("Reading the %s product cards of %s.", self.name, response.url)
        return self._card_products(response)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the category pages listed by a page, then stream its products.

        Args:
            response (Response): The category page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The category page requests, then each product not streamed yet.

        Raises:
            EmptyCatalogueError: If a page holds neither product nor category.
        """
        links = [url for _, _, url in self._cards(response)]
        categories = [url for url in links if self._section(url)[0] == ProximusPageKind.CATEGORY]
        self.logger.info("%d %s category pages to read from %s.", len(categories), self.name, response.url)
        for url in categories:
            yield Request(url)
        if categories and len(categories) == len(links):
            self.logger.info("The %s page %s only lists categories.", self.name, response.url)
            return
        async for item in super().parse(response):
            yield item
