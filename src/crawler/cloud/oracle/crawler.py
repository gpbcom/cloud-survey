from __future__ import annotations

# Standard Library Imports.
import re
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler
from crawler.cloud.oracle.enums import OracleDocsSection, OracleHtmlTag, OraclePanelClass, OracleTocField
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError


class OracleCloudCrawler(BaseCloudCrawler):
    """Oracle Cloud Infrastructure catalogue crawler.

    Attributes:
        HOME_URL (ClassVar[str]): The Oracle website, which hosts the product pages.
        DOCS_ROOT (ClassVar[str]): The English documentation root, the documentation paths are relative to.
        TOC_URL (ClassVar[str]): The table of contents of the infrastructure documentation (JSON).
        DOCS_PRIORITY (ClassVar[int]): The priority of the table of contents, read once the product pages are.
        SERVICES_PANEL (ClassVar[str]): The CSS selector of the services panel of the cloud home page.
        NOT_PRODUCT_NAME (ClassVar[re.Pattern[str]]): The panel links which are not products (SaaS analytics,
            compliance, regions, solutions and category overviews).
        DESCRIPTION_FALLBACKS (ClassVar[Tuple[str, ...]]): The CSS selectors of the documentation page paragraphs
            read when the page has no meta description: the short description, then the first article paragraph.
        DOCS_SECTION (ClassVar[OracleDocsSection]): The table of contents section listing the services.
        DOCS_NOT_SERVICE (ClassVar[re.Pattern[str]]): The documentation entries which are not services (document
            lists, essentials, billing, and the EPM and Fusion SaaS applications).
        DOCS_ALIASES (ClassVar[Dict[str, str]]): The panel names of the services named otherwise in the docs.
        PANEL_CATEGORIES (ClassVar[Tuple[Tuple[OraclePanelClass, OracleHtmlTag], ...]]): The classes of the services
            panel blocks naming a category, with the tag of their heading: the drawer (e.g. `AI and Machine Learning`),
            then its group (e.g. `Generative AI`).

    Notes:
        The main source is the services panel of https://www.oracle.com/cloud/ (behind Akamai, which only lets a
        real browser through): it only gives the product names and links, so each product page is requested and
        its description read from its meta description. The infrastructure documentation table of contents
        completes it with the services missing from the panel, whose documentation home pages are requested the
        same way (the short description or the first paragraph of the page as fallback). It is read after the
        product pages, so that the services already found are not requested again. Missing product pages (HTTP 404)
        are skipped, the documentation then providing the service.
        The categories of a product are the drawer and group headings of the services panel listing it (each of
        them, a product being listed in several drawers), carried by its product page request. The documentation
        table of contents lists the services flat, without category.
    """

    HOME_URL: ClassVar[str] = "https://www.oracle.com"
    DOCS_ROOT: ClassVar[str] = "https://docs.oracle.com/en-us"
    TOC_URL: ClassVar[str] = f"{DOCS_ROOT}/iaas/toc.json"
    DOCS_PRIORITY: ClassVar[int] = -1
    SERVICES_PANEL: ClassVar[str] = 'section.rc105[data-lbl="oci-marchitecture:"]'
    NOT_PRODUCT_NAME: ClassVar[re.Pattern[str]] = re.compile(
        r"solutions$|regions$|sovereign cloud$|^privacy$|compliance$|corporate security$|^oracle fusion .*analytics$|"
        r"analytics mobile app$|capabilities$|^(ai|machine learning) services$",
        re.IGNORECASE,
    )
    DESCRIPTION_FALLBACKS: ClassVar[Tuple[str, ...]] = ("p.shortdesc", "article > p")
    DOCS_SECTION: ClassVar[OracleDocsSection] = OracleDocsSection.INFRASTRUCTURE_SERVICES
    DOCS_NOT_SERVICE: ClassVar[re.Pattern[str]] = re.compile(
        r"all doc|documents?$|documentation$|^service essentials$|^billing|\bepm\b|^fusion ", re.IGNORECASE
    )
    DOCS_ALIASES: ClassVar[Dict[str, str]] = {
        "Block Volume": "Block Volumes",
        "Compute": "Virtual Machines",
        "Container Registry": "Registry",
        "Database": "Base Database Service",
        "Disaster Recovery": "Full Stack Disaster Recovery",
        "DNS and Traffic Management": "DNS Management",
        "Generative AI": "Generative AI Service",
        "IAM with Identity Domains": "Identity and Access Management",
        "IAM without Identity Domains": "Identity and Access Management",
        "Integration 3": "Application Integration",
        "Internet of Things": "IoT Platform",
        "Load Balancer": "Load Balancers",
        "Media Services": "Media Flow",
        "MySQL HeatWave": "HeatWave MySQL",
        "Networking": "Virtual Cloud Networks",
        "NoSQL Database": "NoSQL",
        "Oracle APEX Application Development": "APEX",
        "Vault": "Key Management",
        "VMware Solution": "VMware",
    }

    PANEL_CATEGORIES: ClassVar[Tuple[Tuple[OraclePanelClass, OracleHtmlTag], ...]] = (
        (OraclePanelClass.DRAWER, OracleHtmlTag.H3),
        (OraclePanelClass.GROUP, OracleHtmlTag.H4),
    )

    name = "oracle"
    catalogue_url: ClassVar[str] = f"{HOME_URL}/cloud/"
    complement_urls: ClassVar[Tuple[str, ...]] = (TOC_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Oracle Cloud Infrastructure ", "OCI ", "Oracle ")

    ############################
    # Internal Helpers Methods #
    ############################

    def _complement_request(self, url: str) -> Request:
        """Build the documentation table of contents request, read after the product pages of the panel.

        Args:
            url (str): The table of contents.

        Returns:
            Request: The request, with a priority lower than the product pages one.
        """
        return Request(url, priority=self.DOCS_PRIORITY)

    def _page_description(self, response: Response) -> Optional[str]:
        """Read the description of a product page, or the short description of a documentation page.

        Args:
            response (Response): The product or documentation page.

        Returns:
            Optional[str]: The meta description, else the Open Graph one, else the short description paragraph,
                else the first paragraph of the article (documentation landing pages), `None` when the page has none.
        """
        description = super()._page_description(response)
        for selector in self.DESCRIPTION_FALLBACKS:
            if description is not None:
                break
            if (paragraph := response.css(selector).first) is not None:
                description = self._clean_text(paragraph.get_all_text(separator=" ", strip=True)) or None
        return description

    def _panel_categories(self, anchor: Selector) -> List[str]:
        """Get the categories of a services panel link: the headings of the drawer and group holding it.

        Args:
            anchor (Selector): The panel link.

        Returns:
            List[str]: The drawer heading then the group heading, those present.
        """
        headings: Dict[str, str] = {}
        for ancestor in anchor.iterancestors():
            classes = ancestor.attrib.get(HtmlAttribute.CLASS, "").split()
            for block, tag in self.PANEL_CATEGORIES:
                heading = ancestor.css(tag).first if block in classes else None
                if heading is not None and block not in headings:
                    headings[block] = self._clean_text(heading.get_all_text(separator=" ", strip=True))
        return [headings[block] for block, _ in self.PANEL_CATEGORIES if headings.get(block)]

    def _panel_links(self, response: Response) -> List[Tuple[str, str, List[str]]]:
        """Read the product links of the services panel of the cloud home page.

        Args:
            response (Response): The cloud home page.

        Returns:
            List[Tuple[str, str, List[str]]]: The product names, absolute page URLs and categories, in panel order.

        Raises:
            CatalogueFormatError: If the page has no services panel, or if the panel lists no link.
        """
        panel = response.css(self.SERVICES_PANEL).first
        blocks = panel.css("div.rc105w1") if panel is not None else []
        anchors = blocks[1].css("ul.rc105linklist a[href]") if len(blocks) > 1 else []
        if not anchors:
            self.logger.error("The %s catalogue page %s has no services panel links.", self.name, response.url)
            raise CatalogueFormatError(self.name, response.url, "the services panel lists no link")
        links: List[Tuple[str, str, List[str]]] = []
        for anchor in anchors:
            name = self._clean_text(anchor.get_all_text(separator=" ", strip=True))
            href = re.sub(r"(%20)+$", "", anchor.attrib.get(HtmlAttribute.HREF, "").strip())
            links.append((name, urljoin(response.url, href), self._panel_categories(anchor)))
        self.logger.debug("%d links in the services panel of %s.", len(links), response.url)
        return links

    def _panel_requests(self, response: Response) -> List[Request]:
        """Request the product pages of the services panel, skipping the documentation links and non-products.

        Args:
            response (Response): The cloud home page.

        Returns:
            List[Request]: The product page requests, once per product, with the categories of all its links.

        Raises:
            CatalogueFormatError: If the page has no services panel, or if the panel lists no link.

        Notes:
            The links of a product share one categories list (by name and URL key), completed by its later links:
            the requests are built once the whole panel is read, filed under these lists (`PRODUCT_CATEGORIES`
            meta).
        """
        listed: Dict[str, List[str]] = {}
        pages: List[Tuple[str, str, List[str]]] = []
        for name, url, categories in self._panel_links(response):
            keys = (self._name_key(name), self._url_key(url))
            known = next((listed[key] for key in keys if key in listed), None)
            if urlparse(url).netloc != urlparse(self.HOME_URL).netloc:
                self.logger.debug("Skipping the panel link %r (%s), not a product page.", name, url)
            elif self.NOT_PRODUCT_NAME.search(name):
                self.logger.debug("Skipping the panel link %r (%s), not a product.", name, url)
            elif known is not None:
                self.logger.debug("Skipping the panel link %r (%s), already listed.", name, url)
                known.extend(category for category in categories if category not in known)
            else:
                listed.update(dict.fromkeys(keys, categories))
                pages.append((url, name, categories))
        requests = [
            request
            for url, name, categories in pages
            if (request := self._product_page_request(url, name, categories=categories)) is not None
        ]
        self.logger.info("%d %s product pages to read from the services panel.", len(requests), self.name)
        return requests

    def _docs_entries(self, response: Response) -> Iterator[Tuple[str, str]]:
        """Read the services of the documentation table of contents.

        Args:
            response (Response): The table of contents (JSON).

        Yields:
            Iterator[Tuple[str, str]]: Each service name and documentation home page URL.

        Raises:
            CatalogueFormatError: If the response is not JSON, or if it has no services section.
        """
        data = self._as_object(self._json_body(response))
        pages = self._as_object(data.get(OracleTocField.PAGES))
        bases = self._as_object(data.get(OracleTocField.SOURCE_BASEPATHS))
        tree = data.get(OracleTocField.TREE)
        nodes = [self._as_object(node) for node in tree] if isinstance(tree, list) else []
        section = next(
            (
                node
                for node in nodes
                if self._as_object(pages.get(str(node.get(OracleTocField.PAGE_ID)))).get(OracleTocField.TITLE)
                == self.DOCS_SECTION
            ),
            None,
        )
        children = section.get(OracleTocField.CHILDREN) if section is not None else None
        if not isinstance(children, list):
            self.logger.error(
                "The %s table of contents %s has no %r section.", self.name, response.url, self.DOCS_SECTION
            )
            raise CatalogueFormatError(self.name, response.url, f"the {self.DOCS_SECTION!r} section is missing")
        self.logger.debug("%d entries in the %r section of %s.", len(children), self.DOCS_SECTION, response.url)
        for child in children:
            page = self._as_object(pages.get(str(self._as_object(child).get(OracleTocField.PAGE_ID))))
            name = self._clean_text(self._as_text(page.get(OracleTocField.TITLE)))
            path = self._as_text(page.get(OracleTocField.PATH))
            base = self._as_text(bases.get(str(page.get(OracleTocField.SOURCE))))
            if not name or not path or base is None:
                self.logger.debug("Skipping the documentation entry %r, without a page.", name)
                continue
            yield name, urljoin(f"{self.DOCS_ROOT}{base.rstrip('/')}/", path)

    def _docs_requests(self, response: Response) -> List[Request]:
        """Request the documentation pages of the services missing from the panel.

        Args:
            response (Response): The table of contents (JSON).

        Returns:
            List[Request]: The documentation page requests.

        Raises:
            CatalogueFormatError: If the response is not JSON, or if it has no services section.
        """
        requests: List[Request] = []
        for name, url in self._docs_entries(response):
            known = (name, self.DOCS_ALIASES.get(name, name))
            if self.DOCS_NOT_SERVICE.search(name):
                self.logger.debug("Skipping the documentation entry %r, not a service.", name)
            elif any(self._name_key(alias) in self.seen_products for alias in known):
                self.logger.debug("Skipping the documentation entry %r, already streamed.", name)
            elif request := self._product_page_request(url, name):
                requests.append(request)
        self.logger.info("%d %s documentation pages to read from the table of contents.", len(requests), self.name)
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Request the product pages of the panel or of the documentation, or stream the product of a page.

        Args:
            response (Response): The cloud home page, the documentation table of contents, or a product page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The product page requests, or the product of a product page.

        Raises:
            CatalogueFormatError: If the cloud home page has no services panel links,
                or if the table of contents is not JSON or has no services section.
        """
        if self.PRODUCT_PAGE in response.meta:
            async for item in super().parse(response):
                yield item
            return
        is_docs = urlparse(response.url).netloc == urlparse(self.TOC_URL).netloc
        for request in self._docs_requests(response) if is_docs else self._panel_requests(response):
            yield request
