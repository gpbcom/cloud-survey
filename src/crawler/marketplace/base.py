from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, List, Optional, Sequence, Union

# Third Party Imports.
from pydantic import JsonValue, ValidationError
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

# First Party Imports.
from classifier.software_classifier import SoftwareClassifier
from crawler.cloud.base import BaseCloudCrawler
from crawler.enums import HttpMethod, RequestMeta
from crawler.exception import EmptyCatalogueError, ParseNotImplementedError
from crawler.tls.ca_bundle import CaBundle
from models.cloud.enums import DateCaveat, DeliveryMethod
from models.cloud.software.marketplace_category import MarketplaceCategory
from models.cloud.software.marketplace_software import MarketplaceSoftware


class BaseMarketplaceCrawler(BaseCloudCrawler):
    """Base class for the cloud provider marketplace crawlers: the software listed in a marketplace.

    Attributes:
        MAY_BE_EMPTY (ClassVar[str]): The meta key of the pages which may list no software (e.g. a last page).
        NAME_LIMIT (ClassVar[int]): The longest software name kept, longer ones are shortened.
        lazy_browser (ClassVar[bool]): The stealth browser is only started when a request uses it.
        page_limit (ClassVar[Optional[int]]): The maximum number of pages read per paginated source, `None` for all of
            them (e.g. to keep the live tests short).
        classifier (SoftwareClassifier): The classifier giving the software audiences.
        software_categories (Dict[str, List[str]]): The marketplace categories of each streamed software, by identity.
        software_category_paths (Dict[str, List[MarketplaceCategory]]): The categories of the marketplace taxonomy of
            each streamed software (with their parents), by identity.

    Notes:
        The marketplaces are mostly read through the JSON APIs their pages use: the requests go through an HTTP
        session (`<name>-http`, browser impersonation), which is the default session. The stealth browser
        (`<name>-session`) is only started for the pages which need it. A software listed again with new marketplace
        categories (e.g. by a category query) is streamed again, with all its categories and classified again: the
        runner keeps its last version. The categories are kept twice: as the flat labels of the marketplace (which
        the classifier reads), and as paths of the marketplace taxonomy, each category with its parents
        (`MarketplaceCategory`), when the marketplace gives its taxonomy.
    """

    MAY_BE_EMPTY: ClassVar[str] = RequestMeta.MAY_BE_EMPTY
    NAME_LIMIT: ClassVar[int] = 300

    lazy_browser: ClassVar[bool] = True
    page_limit: ClassVar[Optional[int]] = None

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
        super().__init__(crawldir=crawldir, interval=interval)
        self.classifier = classifier if classifier else SoftwareClassifier()
        self.software_categories: Dict[str, List[str]] = {}
        self.software_category_paths: Dict[str, List[MarketplaceCategory]] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _http_session_id(self) -> str:
        """Get the identifier of the HTTP session.

        Returns:
            str: The session identifier, e.g. `aws-http`.
        """
        return f"{self.name}-http"

    def _api_request(
        self,
        url: str,
        method: str = HttpMethod.GET,
        json: Optional[JsonValue] = None,
        headers: Optional[Dict[str, str]] = None,
        meta: Optional[Dict[str, JsonValue]] = None,
        priority: int = 0,
    ) -> Request:
        """Build a request of the HTTP session, e.g. to a JSON API of the marketplace.

        Args:
            url (str): The requested URL.
            method (str): The HTTP method, `GET` or `POST`.
            json (Optional[JsonValue]): The JSON body of a `POST` request.
            headers (Optional[Dict[str, str]]): Extra request headers.
            meta (Optional[Dict[str, JsonValue]]): The request meta, given back with its response.
            priority (int): The request priority.

        Returns:
            Request: The request. It is never filtered as a duplicate, since a `POST` URL may be requested with
                several bodies.
        """
        return Request(
            url,
            sid=self._http_session_id(),
            priority=priority,
            dont_filter=True,
            meta=meta or {},
            method=method,
            json=json,
            headers=headers,
        )

    def _within_page_limit(self, page: int) -> bool:
        """Tell whether a page of a paginated source may be requested.

        Args:
            page (int): The page number, the first page being 1.

        Returns:
            bool: Whether the page is within the page limit (always, without limit).
        """
        if self.page_limit is not None and page > self.page_limit:
            self.logger.info("Page limit (%d) reached: page %d not requested.", self.page_limit, page)
            return False
        return True

    def _category(
        self, path: Sequence[Optional[str]], category_id: Optional[Union[str, int]] = None
    ) -> Optional[MarketplaceCategory]:
        """Build a category of the marketplace taxonomy from scraped labels.

        Args:
            path (Sequence[Optional[str]]): The scraped labels, from the root of the taxonomy to the category (the
                missing levels are skipped).
            category_id (Optional[Union[str, int]]): The identifier (or slug) of the category in the marketplace.

        Returns:
            Optional[MarketplaceCategory]: The category, `None` when no label is usable (logged).
        """
        labels = [label for label in (self._clean_text(level) for level in path) if label]
        if not labels:
            self.logger.debug("No usable label in the category path %r.", list(path))
            return None
        try:
            category = MarketplaceCategory.model_validate(
                {"path": labels, "id": str(category_id) if category_id is not None else None}
            )
        except ValidationError as e:
            self.logger.warning("Skipping the invalid marketplace category %r: %s", labels, e.errors()[0]["msg"])
            return None
        self.logger.debug("Marketplace category of %s: %s.", self.name, category.label())
        return category

    def _build_software(
        self,
        name: Optional[str],
        description: Optional[str],
        url: Optional[str] = None,
        publisher: Optional[str] = None,
        delivery: DeliveryMethod = DeliveryMethod.OTHER,
        marketplace_categories: Sequence[Optional[str]] = (),
        marketplace_category_paths: Sequence[Optional[MarketplaceCategory]] = (),
        added_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        added_caveat: Optional[DateCaveat] = None,
        updated_caveat: Optional[DateCaveat] = None,
    ) -> Optional[MarketplaceSoftware]:
        """Build a classified software from scraped texts, with collapsed whitespaces and texts within the limits.

        Args:
            name (Optional[str]): The scraped software name.
            description (Optional[str]): The scraped software description.
            url (Optional[str]): The software marketplace page, dropped (not the software) when it is not an absolute
                http(s) link.
            publisher (Optional[str]): The scraped software publisher.
            delivery (DeliveryMethod): How the software is delivered.
            marketplace_categories (Sequence[Optional[str]]): The categories given by the marketplace.
            marketplace_category_paths (Sequence[Optional[MarketplaceCategory]]): The categories of the marketplace
                taxonomy, with their parents (see `_category`), the missing ones skipped.
            added_at (Optional[datetime]): When the marketplace says the software was listed, if it does.
            updated_at (Optional[datetime]): When the marketplace says the software was last updated, if it does.
            added_caveat (Optional[DateCaveat]): Why `added_at` may not be the listing date, if it may not.
            updated_caveat (Optional[DateCaveat]): Why `updated_at` may not be a change of the software, if it may not.

        Returns:
            Optional[MarketplaceSoftware]: The software, or `None` (logged) when the scraped texts are invalid.
        """
        clean_name = self._clean_text(name)[: self.NAME_LIMIT]
        clean_description = self._shorten(self._clean_text(description))
        labels = [label for label in (self._clean_text(category) for category in marketplace_categories) if label]
        classification = self.classifier.classify(clean_name, clean_description, labels, delivery)
        categories = classification.audiences
        try:
            return MarketplaceSoftware.model_validate(
                {
                    "name": clean_name,
                    "description": clean_description,
                    "publisher": self._clean_text(publisher) or None,
                    "url": self._valid_url(url, name),
                    "delivery": delivery,
                    "marketplace_categories": labels,
                    "marketplace_category_paths": [path for path in marketplace_category_paths if path] or None,
                    "categories": categories,
                    "added_at": added_at,
                    "added_caveat": added_caveat if added_at else None,
                    "updated_at": updated_at,
                    "updated_caveat": updated_caveat if updated_at else None,
                }
            )
        except ValidationError as e:
            reasons = "; ".join(f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in e.errors())
            self.logger.warning("Skipping the invalid marketplace entry %r (%s).", name, reasons)
            return None

    def _merge_listings(
        self, software: MarketplaceSoftware, labels: List[str], paths: List[MarketplaceCategory]
    ) -> Optional[MarketplaceSoftware]:
        """Merge a software listed again with what its previous listings gave.

        Args:
            software (MarketplaceSoftware): The software listed again.
            labels (List[str]): The marketplace categories of its previous listings.
            paths (List[MarketplaceCategory]): The category paths of its previous listings.

        Returns:
            Optional[MarketplaceSoftware]: The software with every category seen for it, classified again, `None` when
                the new listing brings no new category.
        """
        merged = list(dict.fromkeys([*labels, *software.marketplace_categories]))
        listed = MarketplaceSoftware.model_validate(
            {
                **software.model_dump(),
                "marketplace_categories": merged,
                "marketplace_category_paths": [*paths, *(software.marketplace_category_paths or [])],
            }
        )
        merged_paths = listed.marketplace_category_paths or []
        if merged == labels and merged_paths == paths:
            self.logger.debug("Skipping the duplicated software %r.", software.name)
            return None
        classification = self.classifier.classify(software.name, software.description, merged, software.delivery)
        categories = classification.audiences
        self.logger.debug(
            "New marketplace categories for %r: %s.",
            software.name,
            ", ".join([*merged, *(path.label() for path in merged_paths)]),
        )
        return listed.model_copy(update={"categories": categories})

    def _stream_software(self, software: MarketplaceSoftware) -> Optional[Dict[str, JsonValue]]:
        """Get the item of a software not streamed yet, or streamed with fewer marketplace categories, and log it.

        Args:
            software (MarketplaceSoftware): The extracted software.

        Returns:
            Optional[Dict[str, JsonValue]]: The software as a dictionary, with every marketplace category (and
                category path) seen for it, classified again when they changed. `None` when it brings nothing new.
        """
        identity = software.identity()
        known = self.software_categories.get(identity)
        if known is not None:
            merged = self._merge_listings(software, known, self.software_category_paths.get(identity, []))
            if merged is None:
                return None
            software = merged
        self.software_categories[identity] = list(software.marketplace_categories)
        self.software_category_paths[identity] = list(software.marketplace_category_paths or [])
        self.logger.info(
            "Software extracted from %s: %s (%s) - %s",
            self.name,
            software.name,
            ", ".join(software.categories),
            software.description,
        )
        return software.item_dump()

    ############################
    # Publicly Exposed Methods #
    ############################

    def configure_sessions(self, manager: SessionManager) -> None:
        """Configure the HTTP session, the default one, and the stealth browser session, started when needed.

        Args:
            manager (SessionManager): Consistent scrapling session mechanism.
        """
        super().configure_sessions(manager)
        self.logger.debug("Configuring the HTTP session %s.", self._http_session_id())
        CaBundle(logger=self.logger).install()
        manager.add(
            self._http_session_id(),
            FetcherSession(
                impersonate="chrome",
                timeout=60,
                retries=self.fetch_retries,
                retry_delay=round(self.retry_delay),
            ),
            default=True,
        )

    async def on_start(self, resuming: bool = False) -> None:
        """Forget the software of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.software_categories.clear()
            self.software_category_paths.clear()

    async def on_close(self) -> None:
        """Log the crawl summary."""
        await super().on_close()
        self.logger.info(
            "The %s marketplace crawl is over: %d software streamed.", self.name, len(self.software_categories)
        )

    def extract_software(self, response: Response) -> Iterator[MarketplaceSoftware]:
        """Extract the software of a marketplace page.

        Args:
            response (Response): The marketplace page.

        Returns:
            Iterator[MarketplaceSoftware]: The valid software of the page, duplicates included.

        Raises:
            ParseNotImplementedError: If the crawler does not implement the extraction.
        """
        self.logger.error("The %s crawler does not implement the marketplace extraction.", type(self).__name__)
        raise ParseNotImplementedError(type(self).__name__)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the software of a marketplace page.

        Args:
            response (Response): The marketplace page.

        Yields:
            Dict[str, JsonValue]: Each software not streamed yet (or with new marketplace categories).

        Raises:
            EmptyCatalogueError: If a page holds no valid software at all, unless it may be empty (`MAY_BE_EMPTY`).
        """
        self.logger.debug("Parsing the %s marketplace page %s (HTTP %s).", self.name, response.url, response.status)
        found = streamed = 0
        for software in self.extract_software(response):
            found += 1
            if (item := self._stream_software(software)) is not None:
                streamed += 1
                yield item
        if not found and not response.meta.get(self.MAY_BE_EMPTY):
            self.logger.error("The %s marketplace page %s holds no software.", self.name, response.url)
            raise EmptyCatalogueError(self.name, response.url)
        self.logger.info(
            "%s marketplace page %s parsed: %d software streamed, %d duplicates skipped.",
            self.name,
            response.url,
            streamed,
            found - streamed,
        )
