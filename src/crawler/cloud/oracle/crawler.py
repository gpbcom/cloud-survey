from __future__ import annotations

# Standard Library Imports.
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, FrozenSet, Iterator, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

# Third Party Imports.
from pydantic import JsonValue
from scrapling.parser import Selector
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.cloud.base import BaseCloudCrawler, PriceFact
from crawler.cloud.oracle.enums import (
    OracleDocsSection,
    OracleHtmlTag,
    OraclePanelClass,
    OracleProductsField,
    OracleReleaseNotesField,
    OracleTocField,
)
from crawler.enums import HtmlAttribute
from crawler.exception import CatalogueFormatError
from models.cloud.enums import DateCaveat, PriceModel, PriceSourceKind, PriceUnit
from models.cloud.prices.facts.service_price import ServicePrice
from models.cloud.prices.price_field_check import RawValue
from models.cloud.products.product import CloudProduct


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
        RELEASE_NOTES_ROOT (ClassVar[str]): The infrastructure release notes, the dated source.
        RELEASE_NOTES_SERVICES_URL (ClassVar[str]): The services of the release notes (JSON), each with its slug and
            title.
        RELEASE_NOTES_URL (ClassVar[str]): The release notes page of a service, from its slug: every note of the
            service, newest first.
        RELEASE_NOTES_TITLE (ClassVar[str]): The CSS selector of the title of a release notes page, the service title
            (`All Services` on the page served for an unknown slug).
        RELEASE_NOTE_DATES (ClassVar[str]): The CSS selector of the release dates of the notes of a page.
        RELEASE_NOTE_DATE_FORMAT (ClassVar[str]): The format of the release dates, e.g. `October 19, 2017`.
        RELEASE_NOTES_ALIASES (ClassVar[Dict[str, str]]): The release notes titles of the products named otherwise in
            the release notes (and not by the documentation aliases).
        dates_launches (ClassVar[bool]): The launch of each product is read from its release notes.
        launch_feed_start (ClassVar[Optional[datetime]]): The first months of the release notes, whose earliest notes
            may postdate the launch of the services already offered then.
        PRICES_URL (ClassVar[str]): The public price list API (cetools products), every part with its prices.
        PRICE_CURRENCY (ClassVar[str]): The currency read (the price list localizes every price in ~45 currencies,
            converted from the dollar one).
        METRIC_UNITS (ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit, int], ...]]): The rules normalizing a
            metric, in order: its pattern, its unit and the normalized units in one.
        METRIC_COUNT (ClassVar[re.Pattern[str]]): The count a metric starts with, e.g. `1,000,000` or `5K`.
        MILLION (ClassVar[re.Pattern[str]]): A metric counting by the million (`Million Datapoints`, `1MIL`).
        COUNTABLE_UNITS (ClassVar[FrozenSet[PriceUnit]]): The units a metric count multiplies.
        OCPU (ClassVar[re.Pattern[str]]): A metric per OCPU.
        ARM_OCPU (ClassVar[re.Pattern[str]]): The parts whose OCPU is an Arm core (one vCPU).
        VCPUS_PER_OCPU (ClassVar[int]): The vCPUs of an x86 OCPU (a core, two threads).
        UNBOUNDED_RANGE (ClassVar[int]): The upper bound written for a tier without one.
        release_notes_services (Optional[Dict[str, Tuple[str, str]]]): The slug and title of each service of the
            release notes, by normalized title, read once per crawl (`None` until read).

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
        The launch of a product (`dates_launches`) is the earliest release date of the release notes page of its
        service, found in the release notes services list (read once per crawl) by its title: the launch dates
        catalogue's alias of the product, else its `RELEASE_NOTES_ALIASES` entry, else its name, else the
        documentation names it is known by (`DOCS_ALIASES`), brand prefixes, case and punctuation ignored. An unknown
        slug is answered with the `All Services` page (the notes of the last days), so a page whose title is not the
        service title is ignored. The notes before `launch_feed_start` are qualified `FEED_START`.
        In price mode it reads the public price list API (`PRICES_URL`, `apexapps.oracle.com`, not behind Akamai):
        one price per part in dollars, one per volume tier when the part has several (e.g. the first 10 TB of
        outbound transfer free). Its metric is normalized by ordered rules (`METRIC_UNITS`): an OCPU is two vCPUs
        (one on Arm). The list states its version (`lastUpdated`): an unchanged list is not read again. The prices
        are the same in every region.
    """

    HOME_URL: ClassVar[str] = "https://www.oracle.com"
    PRICES_URL: ClassVar[str] = "https://apexapps.oracle.com/pls/apex/cetools/api/v1/products/"
    PRICE_CURRENCY: ClassVar[str] = "USD"
    METRIC_UNITS: ClassVar[Tuple[Tuple[re.Pattern[str], PriceUnit, int], ...]] = (
        (re.compile(r"\btokens?\b", re.IGNORECASE), PriceUnit.TOKEN, 1),
        (re.compile(r"\bOCPU\b|\bECPU\b|\bvCPU\b|\bCPU Core\b", re.IGNORECASE), PriceUnit.VCPU_HOUR, 1),
        (re.compile(r"\bGPU\b", re.IGNORECASE), PriceUnit.UNIT_HOUR, 1),
        (re.compile(r"\bPerformance Units\b|\bMilliseconds\b", re.IGNORECASE), PriceUnit.OTHER, 1),
        (re.compile(r"\bTerabyte\b.*\bMonth\b", re.IGNORECASE), PriceUnit.GIB_MONTH, 1024),
        (re.compile(r"\bTerabyte\b.*\bHour\b", re.IGNORECASE), PriceUnit.GIB_HOUR, 1024),
        (re.compile(r"\bGB Memory-Seconds\b", re.IGNORECASE), PriceUnit.GIB_SECOND, 1),
        (
            re.compile(r"\b(?:Gigabytes?|Gibibytes?|GB)\b.*\b(?:Transfer\w*|Processed|Retrieved)\b", re.IGNORECASE),
            PriceUnit.GIB,
            1,
        ),
        (re.compile(r"\b(?:Gigabytes?|Gibibytes?|GB)\b.*\bMonth\b", re.IGNORECASE), PriceUnit.GIB_MONTH, 1),
        (re.compile(r"\b(?:Gigabytes?|Gibibytes?|GB)\b.*\bHour\b", re.IGNORECASE), PriceUnit.GIB_HOUR, 1),
        (re.compile(r"\bMinute\b", re.IGNORECASE), PriceUnit.MINUTE, 1),
        (re.compile(r"\bPer Day\b", re.IGNORECASE), PriceUnit.UNIT_HOUR, 24),
        (re.compile(r"\b(?:Messages|Requests) Per Hour\b", re.IGNORECASE), PriceUnit.HOUR, 1),
        (re.compile(r"\bCharacters\b", re.IGNORECASE), PriceUnit.CHARACTER, 1),
        (
            re.compile(
                r"\b(?:Transactions?|Requests?|Search Units|Operations|Datapoints|Messages|Emails|API Calls|"
                r"Invocations|Queries|Events|Records)\b",
                re.IGNORECASE,
            ),
            PriceUnit.REQUEST,
            1,
        ),
        (re.compile(r"\bMonth\b", re.IGNORECASE), PriceUnit.UNIT_MONTH, 1),
        (re.compile(r"\bHour\b", re.IGNORECASE), PriceUnit.HOUR, 1),
        (re.compile(r"^Image$", re.IGNORECASE), PriceUnit.IMAGE, 1),
        (re.compile(r"^Each$|\bSMS\b|^Load Balancer$", re.IGNORECASE), PriceUnit.UNIT, 1),
    )
    METRIC_COUNT: ClassVar[re.Pattern[str]] = re.compile(r"^(\d[\d,]*)\s*(K)?\b")
    MILLION: ClassVar[re.Pattern[str]] = re.compile(r"\bMillion\b|\dMIL\b", re.IGNORECASE)
    COUNTABLE_UNITS: ClassVar[FrozenSet[PriceUnit]] = frozenset(
        {
            PriceUnit.TOKEN,
            PriceUnit.REQUEST,
            PriceUnit.UNIT,
            PriceUnit.IMAGE,
            PriceUnit.MINUTE,
            PriceUnit.CHARACTER,
            PriceUnit.GIB_SECOND,
        }
    )
    OCPU: ClassVar[re.Pattern[str]] = re.compile(r"\bOCPU\b", re.IGNORECASE)
    ARM_OCPU: ClassVar[re.Pattern[str]] = re.compile(r"\b(?:Ampere|A1|A2|A4)\b")
    VCPUS_PER_OCPU: ClassVar[int] = 2
    UNBOUNDED_RANGE: ClassVar[int] = 999_999_999_999
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

    RELEASE_NOTES_ROOT: ClassVar[str] = f"{DOCS_ROOT}/iaas/releasenotes"
    RELEASE_NOTES_SERVICES_URL: ClassVar[str] = f"{RELEASE_NOTES_ROOT}/services.json"
    RELEASE_NOTES_URL: ClassVar[str] = RELEASE_NOTES_ROOT + "/services/{slug}/index.htm"
    RELEASE_NOTES_TITLE: ClassVar[str] = "h1#rntitle"
    RELEASE_NOTE_DATES: ClassVar[str] = "article.vl-releasenote span.vl-relnotedate"
    RELEASE_NOTE_DATE_FORMAT: ClassVar[str] = "%B %d, %Y"
    RELEASE_NOTES_ALIASES: ClassVar[Dict[str, str]] = {
        "Application Integration": "Integration",
        "Autonomous AI Database": "Database: Autonomous Database Serverless",
        "Autonomous AI Database on Exadata Cloud@Customer": "Database: Autonomous Database on Exadata Cloud@Customer",
        "Base Database Service": "Database: Base Database",
        "Big Data Service": "Big Data",
        "Device Data FHIR": "Device Data FHIR Service",
        "DNS Management": "DNS",
        "Exadata Cloud@Customer": "Database: Oracle Exadata Database Service on Cloud@Customer",
        "Exadata Database Service": "Database: Exadata Database Service on Dedicated Infrastructure",
        "Globally Distributed Autonomous AI Database": "Globally Distributed Autonomous Database",
        "NoSQL": "NoSQL Database Cloud",
        "VMware": "Oracle Cloud VMware Solution",
        "Zero Data Loss Autonomous Recovery Service": "Oracle Database Autonomous Recovery Service",
    }

    name = "oracle"
    catalogue_url: ClassVar[str] = f"{HOME_URL}/cloud/"
    complement_urls: ClassVar[Tuple[str, ...]] = (TOC_URL,)
    name_prefixes: ClassVar[Tuple[str, ...]] = ("Oracle Cloud Infrastructure ", "OCI ", "Oracle ")
    dates_launches: ClassVar[bool] = True
    launch_feed_start: ClassVar[Optional[datetime]] = datetime(2017, 6, 1, tzinfo=UTC)

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.release_notes_services: Optional[Dict[str, Tuple[str, str]]] = None

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

    async def _release_notes_index(self) -> Dict[str, Tuple[str, str]]:
        """Read the services of the release notes, once per crawl.

        Returns:
            Dict[str, Tuple[str, str]]: The slug and title of each service, by normalized title, empty when the list
                is missing.

        Raises:
            CatalogueFormatError: If the services list is not JSON (once, the list is then left empty).
        """
        if self.release_notes_services is not None:
            return self.release_notes_services
        self.release_notes_services = {}
        response = await self._fetch_launch_page(self.RELEASE_NOTES_SERVICES_URL)
        if response is None:
            self.logger.warning("The %s release notes services list cannot be read.", self.name)
            return self.release_notes_services
        data = self._json_body(response)
        for entry in data if isinstance(data, list) else []:
            service = self._as_object(entry)
            slug = self._as_text(service.get(OracleReleaseNotesField.SLUG))
            title = self._clean_text(self._as_text(service.get(OracleReleaseNotesField.TITLE)))
            if slug and title:
                self.release_notes_services.setdefault(self._name_key(title), (slug, title))
        self.logger.info("%d services in the %s release notes.", len(self.release_notes_services), self.name)
        return self.release_notes_services

    def _release_notes_service(self, name: str, services: Dict[str, Tuple[str, str]]) -> Optional[Tuple[str, str]]:
        """Find the release notes service of a product.

        Args:
            name (str): The product name.
            services (Dict[str, Tuple[str, str]]): The slug and title of each service, by normalized title.

        Returns:
            Optional[Tuple[str, str]]: The slug and title of the service, `None` when no service has the product's
                title.

        Notes:
            The titles tried are the launch dates catalogue's alias, the `RELEASE_NOTES_ALIASES` entry, the name, then
            the documentation names of the product (`DOCS_ALIASES`), the first one listed winning.
        """
        key = self._name_key(name)
        candidates = [self.launch_aliases.get(key), self.RELEASE_NOTES_ALIASES.get(name), name]
        candidates += [docs for docs, panel in self.DOCS_ALIASES.items() if self._name_key(panel) == key]
        for candidate in candidates:
            service = services.get(self._name_key(candidate)) if candidate else None
            if service is not None:
                return service
        self.logger.debug("No %s release notes service is titled %r.", self.name, name)
        return None

    def _note_date(self, text: str) -> Optional[datetime]:
        """Parse the release date of a note.

        Args:
            text (str): The release date, e.g. `October 19, 2017`.

        Returns:
            Optional[datetime]: The date in UTC, `None` when unreadable or implausible.
        """
        try:
            parsed = datetime.strptime(self._clean_text(text), self.RELEASE_NOTE_DATE_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            self.logger.debug("The %s release note date %r is not a date, it is ignored.", self.name, text)
            return None
        if not self.EARLIEST_DATE <= parsed <= datetime.now(UTC):
            self.logger.warning("The %s release note date %r is out of range, it is ignored.", self.name, text)
            return None
        return parsed

    def _earliest_note(self, response: Response, title: str) -> Optional[datetime]:
        """Read the release date of the earliest note of a service release notes page.

        Args:
            response (Response): The release notes page.
            title (str): The service title, expected as the page title.

        Returns:
            Optional[datetime]: The earliest release date, `None` when the page has no dated note or is not the
                service page (the `All Services` page served for an unknown slug).
        """
        heading = response.css(self.RELEASE_NOTES_TITLE).first
        shown = self._clean_text(heading.get_all_text(separator=" ", strip=True)) if heading is not None else ""
        if self._name_key(shown) != self._name_key(title):
            self.logger.warning("The %s release notes page %s is %r, not %r.", self.name, response.url, shown, title)
            return None
        texts = [span.get_all_text(strip=True) for span in response.css(self.RELEASE_NOTE_DATES)]
        dates = [date for date in (self._note_date(text) for text in texts) if date is not None]
        if not dates:
            self.logger.debug("No dated release note in %s.", response.url)
            return None
        return min(dates)

    async def _launch_source(self, product: CloudProduct) -> Optional[Tuple[datetime, DateCaveat]]:
        """Read the launch of a product from the earliest note of its service release notes.

        Args:
            product (CloudProduct): The product, undated.

        Returns:
            Optional[Tuple[datetime, DateCaveat]]: The launch and its caveat, `None` when no release notes service
                is titled after the product or its page has no dated note.

        Raises:
            CatalogueFormatError: If the release notes services list is not JSON.
        """
        service = self._release_notes_service(product.name, await self._release_notes_index())
        if service is None:
            return None
        slug, title = service
        response = await self._fetch_launch_page(self.RELEASE_NOTES_URL.format(slug=slug))
        launched = self._earliest_note(response, title) if response is not None else None
        if launched is None:
            return None
        self.logger.debug("%r first noted in the %r release notes on %s.", product.name, title, launched.date())
        return self._announced(launched)

    def _metric_unit(self, metric: str, name: str) -> Tuple[PriceUnit, Decimal]:
        """Normalize what a price of the price list is per.

        Args:
            metric (str): Its metric, e.g. `1,000,000 Tokens`, `OCPU Per Hour`.
            name (str): The name of its part (an Arm OCPU is one vCPU, an x86 one two).

        Returns:
            Tuple[PriceUnit, Decimal]: The normalized unit, from the first matching `METRIC_UNITS` rule, and the
                normalized units in one: the rule's, times the count the metric starts with for a countable unit
                (`10,000 Transactions`, `Million Datapoints`), times the vCPUs of an OCPU.
        """
        for pattern, unit, factor in self.METRIC_UNITS:
            if not pattern.search(metric):
                continue
            total = Decimal(factor)
            count = self.METRIC_COUNT.match(metric)
            if unit in self.COUNTABLE_UNITS and count is not None:
                total *= Decimal(count[1].replace(",", "")) * (1000 if count[2] else 1)
            elif unit in self.COUNTABLE_UNITS and self.MILLION.search(metric):
                total *= Decimal(1_000_000)
            if self.OCPU.search(metric):
                total *= 1 if self.ARM_OCPU.search(name) else self.VCPUS_PER_OCPU
            return unit, total
        self.logger.debug("The Oracle price metric %r has no known unit: kept as other.", metric)
        return PriceUnit.OTHER, Decimal(1)

    def _part_prices(self, part: Dict[str, JsonValue]) -> Iterator[ServicePrice]:
        """Read the prices of a part of the price list, in the currency read.

        Args:
            part (Dict[str, JsonValue]): The part.

        Yields:
            ServicePrice: One price per volume tier (a free first tier as free).
        """
        number = part.get(OracleProductsField.PART_NUMBER)
        localizations = part.get(OracleProductsField.CURRENCY_LOCALIZATIONS)
        prices: List[JsonValue] = []
        for localization in localizations if isinstance(localizations, list) else []:
            listed = localization.get(OracleProductsField.PRICES) if isinstance(localization, dict) else None
            if (
                isinstance(localization, dict)
                and localization.get(OracleProductsField.CURRENCY_CODE) == self.PRICE_CURRENCY
                and isinstance(listed, list)
            ):
                prices = listed
                break
        if not prices:
            self.logger.warning("The Oracle part %s has no %s price.", number, self.PRICE_CURRENCY)
            return
        metric = str(part.get(OracleProductsField.METRIC_NAME) or "")
        name = str(part.get(OracleProductsField.DISPLAY_NAME) or "")
        unit, factor = self._metric_unit(metric, name)
        tiered = len(prices) > 1
        for entry in prices:
            value = entry.get(OracleProductsField.VALUE) if isinstance(entry, dict) else None
            if not isinstance(value, (int, float)) or not isinstance(entry, dict):
                self.logger.debug("A price of the Oracle part %s has no value: skipped.", number)
                continue
            price = Decimal(str(value))
            least = entry.get(OracleProductsField.RANGE_MIN)
            most = entry.get(OracleProductsField.RANGE_MAX)
            start = least if isinstance(least, (int, float)) else 0
            fields: Dict[str, RawValue] = {
                "sku_key": f"{number}/{start}" if tiered else number,
                "service": part.get(OracleProductsField.SERVICE_CATEGORY),
                "family": part.get(OracleProductsField.SERVICE_CATEGORY),
                "attributes": {
                    "part_number": number,
                    OracleProductsField.DISPLAY_NAME.value: name,
                    OracleProductsField.MODEL.value: entry.get(OracleProductsField.MODEL),
                },
                "unit": unit,
                "unit_raw": metric,
                "unit_factor": factor,
                "price": price,
                "currency": self.PRICE_CURRENCY,
                "model": PriceModel.FREE if price == 0 else PriceModel.ON_DEMAND,
                "tier_start": Decimal(str(start)),
                "tier_end": (
                    Decimal(str(most)) if isinstance(most, (int, float)) and most < self.UNBOUNDED_RANGE else None
                ),
                "source_url": self.PRICES_URL,
                "source_kind": PriceSourceKind.API,
            }
            fact = self._price_fact(fields)
            if fact is not None:
                yield fact

    async def _price_requests(self) -> AsyncGenerator[Request]:
        """Request the price list.

        Yields:
            Request: The request of the price list.
        """
        self.logger.info("Reading the Oracle Cloud prices from %s.", self.PRICES_URL)
        yield self._price_request(self.PRICES_URL)

    async def _extract_prices(self, response: Response) -> AsyncGenerator[PriceFact]:
        """Read the prices of the price list, unless it is unchanged since its last read.

        Args:
            response (Response): The price list.

        Yields:
            PriceFact: The prices of each part.

        Raises:
            CatalogueFormatError: If the price list lists no parts.
        """
        data = self._json_body(response)
        items = data.get(OracleProductsField.ITEMS) if isinstance(data, dict) else None
        if not isinstance(data, dict) or not isinstance(items, list):
            self.logger.error("The Oracle price list %s lists no parts.", response.url)
            raise CatalogueFormatError(self.name, response.url, "the price list lists no parts")
        version = data.get(OracleProductsField.LAST_UPDATED)
        version = version if isinstance(version, str) else None
        if self._price_unchanged(self.PRICES_URL, version=version):
            return
        found = 0
        for part in items:
            for fact in self._part_prices(part) if isinstance(part, dict) else iter(()):
                found += 1
                yield fact
        self._record_price_source(self.PRICES_URL, found, version=version)
        self.logger.info("The Oracle price list (%s) is read: %d prices of %d parts.", version, found, len(items))

    ############################
    # Publicly Exposed Methods #
    ############################

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the release notes services of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.release_notes_services = None
            self.logger.debug("The %s release notes services will be read again.", self.name)

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
        self.logger.debug(
            "Reading the %s %s %s.", self.name, "documentation contents" if is_docs else "products panel", response.url
        )
        for request in self._docs_requests(response) if is_docs else self._panel_requests(response):
            yield request
