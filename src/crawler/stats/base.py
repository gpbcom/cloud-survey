from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, Optional, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue
from scrapling.fetchers import FetcherSession
from scrapling.spiders import Request, Response
from scrapling.spiders.session import SessionManager

from crawler.cloud.base import BaseCloudCrawler
from crawler.exception import ParseNotImplementedError

# First Party Imports.
from crawler.tls.ca_bundle import CaBundle
from models.cloud.enums import MarketRegion, MarketSegment
from models.stats.market_report import MarketReport

ReportKey = Tuple[str, MarketRegion, MarketSegment]


class BaseStatsCrawler(BaseCloudCrawler):
    """Base class for the cloud market statistics crawlers: the figures published by a market research firm.

    Attributes:
        source (ClassVar[str]): The market research firm, e.g. `Synergy Research Group`.
        lazy_browser (ClassVar[bool]): The stealth browser is only started when a request uses it.
        reports (Dict[ReportKey, MarketReport]): The reports streamed so far, by period, region and segment.

    Notes:
        The pages are read through an HTTP session (`<name>-http`, browser impersonation), the default session. Several
        articles may publish figures of the same period, region and segment (e.g. the quarterly release and a share
        trend article): a report is streamed again when it is more complete than the one streamed before, and the
        runner keeps the last version.
    """

    source: ClassVar[str] = ""
    lazy_browser: ClassVar[bool] = True

    def __init__(self, crawldir: Optional[Union[str, Path]] = None, interval: float = 300.0) -> None:
        """Initialize the crawler.

        Args:
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.
        """
        super().__init__(crawldir=crawldir, interval=interval)
        self.reports: Dict[ReportKey, MarketReport] = {}

    ############################
    # Internal Helpers Methods #
    ############################

    def _http_session_id(self) -> str:
        """Get the identifier of the HTTP session.

        Returns:
            str: The session identifier, e.g. `synergy-http`.
        """
        return f"{self.name}-http"

    def _completeness(self, report: MarketReport) -> Tuple[int, int, int, int]:
        """Rate how complete a report is, to keep the best report of a period, region and segment.

        Args:
            report (MarketReport): The report.

        Returns:
            Tuple[int, int, int, int]: The number of shares, whether the market size is known, whether the growth is
                known and the number of mentions: the greater, the more complete.
        """
        return (
            len(report.shares),
            report.market_size_bn is not None,
            report.growth_pct is not None,
            len(report.mentions),
        )

    def _stream_report(self, report: MarketReport) -> Optional[Dict[str, JsonValue]]:
        """Get the item of a report not streamed yet, or more complete than the one streamed before, and log it.

        Args:
            report (MarketReport): The extracted report.

        Returns:
            Optional[Dict[str, JsonValue]]: The report as a dictionary, `None` when it brings nothing new.
        """
        key = (report.period, report.region, report.segment)
        known = self.reports.get(key)
        if known is not None and self._completeness(report) <= self._completeness(known):
            self.logger.debug("Skipping the %s %s %s report of %s: not more complete.", *key, report.source_url)
            return None
        self.reports[key] = report
        shares = ", ".join(f"{share.player} {share.share_pct:g}%" for share in report.shares) or "no share"
        self.logger.info(
            "Market report extracted from %s: %s %s %s, size %s bn %s (%s)",
            self.name,
            report.period,
            report.region,
            report.segment,
            report.market_size_bn,
            report.currency,
            shares,
        )
        return report.model_dump(mode="json")

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
        """Forget the reports of a previous crawl, unless the crawl is resumed.

        Args:
            resuming (bool): Whether the crawl is resumed from a checkpoint.
        """
        await super().on_start(resuming=resuming)
        if not resuming:
            self.reports.clear()

    async def on_close(self) -> None:
        """Log the crawl summary."""
        await super().on_close()
        self.logger.info("The %s statistics crawl is over: %d market reports.", self.name, len(self.reports))

    def extract_reports(self, response: Response) -> Iterator[MarketReport]:
        """Extract the market reports of an article.

        Args:
            response (Response): The article.

        Returns:
            Iterator[MarketReport]: The valid reports of the article, possibly none (not every article has figures).

        Raises:
            ParseNotImplementedError: If the crawler does not implement the extraction.
        """
        self.logger.error("The %s crawler does not implement the market report extraction.", type(self).__name__)
        raise ParseNotImplementedError(type(self).__name__)

    async def parse(self, response: Response) -> AsyncGenerator[Union[Dict[str, JsonValue], Request]]:
        """Stream the market reports of an article: the new ones, or the more complete ones.

        Args:
            response (Response): The article.

        Yields:
            Dict[str, JsonValue]: Each new or more complete report, as a dictionary.
        """
        self.logger.debug("Parsing the %s article %s (HTTP %s).", self.name, response.url, response.status)
        found = streamed = 0
        for report in self.extract_reports(response):
            found += 1
            if (item := self._stream_report(report)) is not None:
                streamed += 1
                yield item
        self.logger.info(
            "%s article %s parsed: %d market reports, %d streamed.", self.name, response.url, found, streamed
        )
