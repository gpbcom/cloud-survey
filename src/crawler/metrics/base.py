from __future__ import annotations

# Standard Library Imports.
import os
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, Optional, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from crawler.cloud.base import BaseCloudCrawler
from crawler.enums import RequestMeta
from crawler.exception import ParseNotImplementedError

# First Party Imports.
from crawler.metrics.catalog_loader import CollectorCatalogLoader
from crawler.tls.ca_bundle import CaBundle
from models.cloud.enums import CloudProvider
from models.drivers.collectors.collector_catalog import CollectorCatalog
from models.drivers.enums import MetricSource
from models.drivers.facts.capex_fact import CapexFact
from models.drivers.facts.company_fact import CompanyFact
from models.drivers.facts.network_fact import NetworkFact
from models.drivers.facts.repository_fact import RepositoryFact

type MetricFact = Union[CapexFact, CompanyFact, NetworkFact, RepositoryFact]


class BaseMetricsCrawler(BaseCloudCrawler):
    """Base class for the crawlers of the provider metrics the catalogues do not give (SEC EDGAR, Wikidata…).

    Attributes:
        PROVIDER (ClassVar[str]): The meta key holding the provider a document is read for.
        source (ClassVar[MetricSource]): The source of the facts crawled.
        lazy_browser (ClassVar[bool]): The stealth browser is only started when a request uses it (never here).
        catalog (CollectorCatalog): Where each provider is found at the source.
        facts (int): The facts streamed so far.

    Notes:
        - The sources are public JSON APIs read through an HTTP session (`<name>-http`), the default one, without
          the stealth headers: each request sends the user agent of the catalogue (SEC EDGAR asks for a contact).
        - A crawler streams the facts as the source states them (a filing fact, a star count, the exchanges of a
          network). Turning them into the measures of the providers (quarters, age, counts) is left to
          `analytics.metrics`.
    """

    PROVIDER: ClassVar[str] = RequestMeta.METRIC_PROVIDER
    source: ClassVar[MetricSource] = MetricSource.MANUAL
    lazy_browser: ClassVar[bool] = True

    def __init__(
        self,
        catalog: Optional[CollectorCatalog] = None,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
    ) -> None:
        """Initialize the crawler.

        Args:
            catalog (Optional[CollectorCatalog]): Where each provider is found, `conf/metrics/collectors.yaml` by
                default.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            CollectorCatalogError: If the default catalogue cannot be loaded.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.catalog = catalog if catalog else CollectorCatalogLoader(self.logger).load()
        self.facts = 0

    ############################
    # Internal Helpers Methods #
    ############################

    def _http_session_id(self) -> str:
        """Get the identifier of the HTTP session.

        Returns:
            str: The session identifier, e.g. `edgar-http`.
        """
        return f"{self.name}-http"

    def _secret(self, variable: str) -> Optional[str]:
        """Read a secret from the environment (never from a file).

        Args:
            variable (str): The name of the environment variable.

        Returns:
            Optional[str]: Its value, `None` when unset or blank.
        """
        value = os.environ.get(variable, "").strip() if variable else ""
        return value or None

    def _headers(self, accept: str) -> Dict[str, str]:
        """Build the headers of a request: the user agent of the catalogue, and the media type asked for.

        Args:
            accept (str): The media type asked for.

        Returns:
            Dict[str, str]: The headers.
        """
        return {"User-Agent": self.catalog.user_agent, "Accept": accept}

    def _metric_request(
        self, url: str, headers: Dict[str, str], provider: Optional[CloudProvider] = None, **meta: JsonValue
    ) -> Request:
        """Build a request of the HTTP session.

        Args:
            url (str): The requested URL.
            headers (Dict[str, str]): The request headers (the user agent replaces the impersonated one).
            provider (Optional[CloudProvider]): The provider the document is read for, if a single one.
            **meta (JsonValue): More request meta, given back with the response.

        Returns:
            Request: The request.
        """
        if provider is not None:
            meta[self.PROVIDER] = provider.value
        return Request(
            url,
            sid=self._http_session_id(),
            priority=self.PRIMARY_PRIORITY,
            meta=dict(meta),
            headers=headers,
        )

    def _provider(self, response: Response) -> Optional[CloudProvider]:
        """Get the provider a document was read for.

        Args:
            response (Response): The document.

        Returns:
            Optional[CloudProvider]: The provider of its request, `None` when unknown.
        """
        value = response.meta.get(self.PROVIDER)
        try:
            return CloudProvider(str(value)) if value else None
        except ValueError:
            self.logger.warning("Unknown provider %r of the %s document %s.", value, self.name, response.url)
            return None

    ############################
    # Publicly Exposed Methods #
    ############################

    def configure_sessions(self, manager: SessionManager) -> None:
        """Configure the HTTP session, the default one, and the stealth browser session, never started.

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
                stealthy_headers=False,
                timeout=60,
                retries=self.fetch_retries,
                retry_delay=round(self.retry_delay),
            ),
            default=True,
        )

    async def on_start(self, resuming: bool = False) -> None:
        """Count the facts from zero, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.facts = 0

    async def on_close(self) -> None:
        """Log the crawl summary."""
        await super().on_close()
        self.logger.info("The %s metrics crawl is over: %d facts.", self.name, self.facts)

    def extract_facts(self, response: Response) -> Iterator[MetricFact]:
        """Extract the facts of a document.

        Args:
            response (Response): The document.

        Returns:
            Iterator[MetricFact]: The valid facts of the document.

        Raises:
            ParseNotImplementedError: If the crawler does not implement the extraction.
        """
        self.logger.error("The %s crawler does not implement the fact extraction.", type(self).__name__)
        raise ParseNotImplementedError(type(self).__name__)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the facts of a document.

        Args:
            response (Response): The document.

        Yields:
            Dict[str, JsonValue]: Each fact, as a dictionary.
        """
        self.logger.debug("Parsing the %s document %s (HTTP %s).", self.name, response.url, response.status)
        found = 0
        for fact in self.extract_facts(response):
            found += 1
            yield fact.model_dump(mode="json")
        self.facts += found
        self.logger.info("%s document %s parsed: %d facts.", self.name, response.url, found)
