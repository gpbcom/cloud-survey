from __future__ import annotations

# Standard Library Imports.
import re
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Set, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.spiders import Request, Response

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.krystal.enums import KrystalListingField, KrystalNextDataField, KrystalRequestMeta
from crawler.exception import EmptyCatalogueError
from crawler.marketplace.base import BaseMarketplaceCrawler
from models.cloud.enums import DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class KrystalMarketplaceCrawler(BaseMarketplaceCrawler):
    """Krystal marketplace crawler: the applications installed in one click on the Krystal web hosting.

    Attributes:
        HOSTING_URL (ClassVar[str]): The prefix of the category and application pages, followed by their slug.
        SLUG (ClassVar[re.Pattern[str]]): A valid category or application slug.
        requested_urls (Set[str]): The category and application pages already requested.

    Notes:
        The category pages `https://krystal.io/hosting/{cms|crm|ecommerce|forum|billingsystems|blog|php}` (Next.js,
        read over HTTP) list their applications in `__NEXT_DATA__` (`props.pageProps.frameworks[]`: name, slug,
        categories and installation type, `cpanel` or `wordpress`, both installed in one click). The listings have
        no description: each application page `https://krystal.io/hosting/{slug}` is read (one request per
        application) for its name, its categories (all of them, an application may be listed in several categories)
        and its meta description (`pageProps.meta.description`). Some applications have a dedicated product page
        (e.g. WooCommerce) giving only the description: the listing gives the name and categories. An application
        page redirected elsewhere (e.g. Mahara to the hosting home page) is skipped, it would describe another page.
        The category slugs given by the listings which are not known yet are requested too. The pages give no
        publisher. The marketplace taxonomy is flat: each category path is a category name, identified by its slug.
    """

    HOSTING_URL: ClassVar[str] = "https://krystal.io/hosting/"
    SLUG: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    name = "krystal-marketplace"
    catalogue_url: ClassVar[str] = f"{HOSTING_URL}cms"
    complement_urls: ClassVar[Tuple[str, ...]] = (
        f"{HOSTING_URL}crm",
        f"{HOSTING_URL}ecommerce",
        f"{HOSTING_URL}forum",
        f"{HOSTING_URL}billingsystems",
        f"{HOSTING_URL}blog",
        f"{HOSTING_URL}php",
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
        self.requested_urls: Set[str] = {self.catalogue_url, *self.complement_urls}

    ############################
    # Internal Helpers Methods #
    ############################

    def _page_props(self, response: Response) -> Dict[str, JsonValue]:
        """Read the page properties of a category or application page.

        Args:
            response (Response): The page.

        Returns:
            Dict[str, JsonValue]: The `props.pageProps` object, empty when missing.
        """
        return self._as_object(
            self._as_object(self._next_data(response).get(KrystalNextDataField.PROPS)).get(
                KrystalNextDataField.PAGE_PROPS
            )
        )

    def _category_labels(self, categories: JsonValue) -> List[str]:
        """Read the labels of a list of categories.

        Args:
            categories (JsonValue): The categories, e.g. `[{"name": "CMS", "slug": "cms"}]`.

        Returns:
            List[str]: The category names, e.g. `["CMS"]`.
        """
        items = categories if isinstance(categories, list) else []
        return [
            name
            for name in (self._as_text(self._as_object(item).get(KrystalNextDataField.NAME)) for item in items)
            if name
        ]

    def _category_paths(self, categories: JsonValue) -> List[Optional[MarketplaceCategory]]:
        """Build the marketplace taxonomy categories of a list of categories.

        Args:
            categories (JsonValue): The categories, e.g. `[{"name": "CMS", "slug": "cms"}]`.

        Returns:
            List[Optional[MarketplaceCategory]]: One single level category per category, identified by its slug (else
                its identifier), `None` for the categories without a usable name.
        """
        items = categories if isinstance(categories, list) else []
        paths: List[Optional[MarketplaceCategory]] = []
        for category in map(self._as_object, items):
            identifier = self._as_text(category.get(KrystalNextDataField.SLUG)) or self._as_text(
                category.get(KrystalNextDataField.ID)
            )
            paths.append(self._category([self._as_text(category.get(KrystalNextDataField.NAME))], identifier))
        self.logger.debug("%d %s category paths read from %d categories.", len(paths), self.name, len(items))
        return paths

    def _page_url(self, slug: Optional[str], kind: str) -> Optional[str]:
        """Get the URL of a category or application page not requested yet, and remember it.

        Args:
            slug (Optional[str]): The page slug, e.g. `wordpress`.
            kind (str): The kind of page, for the logs.

        Returns:
            Optional[str]: The page URL, `None` when the slug is invalid or the page already requested.
        """
        if not slug or not self.SLUG.match(slug):
            self.logger.debug("Ignoring the invalid %s %s slug %r.", self.name, kind, slug)
            return None
        url = f"{self.HOSTING_URL}{slug}"
        if url in self.requested_urls:
            return None
        self.requested_urls.add(url)
        return url

    def _category_requests(self, response: Response) -> List[Request]:
        """Request the application pages of a category page, and the category pages not known yet.

        Args:
            response (Response): The category page.

        Returns:
            List[Request]: The requests of the pages not requested yet.

        Raises:
            EmptyCatalogueError: If the category page lists no application.
        """
        frameworks = self._page_props(response).get(KrystalNextDataField.FRAMEWORKS)
        if not isinstance(frameworks, list) or not frameworks:
            self.logger.error("The %s category page %s lists no application.", self.name, response.url)
            raise EmptyCatalogueError(self.name, response.url)
        requests: List[Request] = []
        for framework in map(self._as_object, frameworks):
            categories = framework.get(KrystalNextDataField.CATEGORIES)
            for category in map(self._as_object, categories if isinstance(categories, list) else []):
                if url := self._page_url(self._as_text(category.get(KrystalNextDataField.SLUG)), "category"):
                    requests.append(Request(url))
            if url := self._page_url(self._as_text(framework.get(KrystalNextDataField.SLUG)), "application"):
                listing: Dict[str, JsonValue] = {
                    KrystalListingField.URL: url,
                    KrystalListingField.NAME: framework.get(KrystalNextDataField.NAME),
                    KrystalListingField.CATEGORIES: categories,
                }
                requests.append(Request(url, meta={KrystalRequestMeta.LISTING: listing, self.MAY_BE_EMPTY: True}))
        self.logger.info(
            "%s category page %s: %d applications listed, %d new pages requested.",
            self.name,
            response.url,
            len(frameworks),
            len(requests),
        )
        return requests

    ############################
    # Publicly Exposed Methods #
    ############################

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the application of an application page, completed by its listing.

        Args:
            response (Response): The application page.

        Yields:
            Iterator[MarketplaceSoftware]: The application, if valid and the page was not redirected.
        """
        listing = self._as_object(response.meta.get(KrystalRequestMeta.LISTING))
        url = self._as_text(listing.get(KrystalListingField.URL)) or response.url
        if response.url.rstrip("/") != url.rstrip("/"):
            self.logger.warning(
                "Skipping the %s application %r: its page %s is redirected to %s.",
                self.name,
                listing.get(KrystalListingField.NAME),
                url,
                response.url,
            )
            return
        props = self._page_props(response)
        labels = self._category_labels(props.get(KrystalNextDataField.CATEGORIES)) + self._category_labels(
            listing.get(KrystalListingField.CATEGORIES)
        )
        paths = self._category_paths(props.get(KrystalNextDataField.CATEGORIES)) + self._category_paths(
            listing.get(KrystalListingField.CATEGORIES)
        )
        description = self._as_text(
            self._as_object(props.get(KrystalNextDataField.META)).get(KrystalNextDataField.DESCRIPTION)
        )
        software = self._build_software(
            self._as_text(props.get(KrystalNextDataField.NAME)) or self._as_text(listing.get(KrystalListingField.NAME)),
            description or self._page_description(response),
            url,
            delivery=DeliveryMethod.ONE_CLICK_APP,
            marketplace_categories=labels,
            marketplace_category_paths=paths,
        )
        if software is not None:
            yield software

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the application of an application page, or request the pages listed by a category page.

        Args:
            response (Response): The application or category page.

        Yields:
            Union[Dict[str, JsonValue], Request]: The application, else the page requests of a category page.
        """
        if KrystalRequestMeta.LISTING in response.meta:
            self.logger.debug("Reading the %s application page %s.", self.name, response.url)
            async for item in super().parse(response):
                yield item
            return
        self.logger.debug("Reading the %s category page %s.", self.name, response.url)
        for request in self._category_requests(response):
            yield request
