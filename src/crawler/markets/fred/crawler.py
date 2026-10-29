from __future__ import annotations

# Standard Library Imports.
import csv
import io
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Dict, Iterator, Optional, Union
from urllib.parse import urlencode

# Third Party Imports.
from pydantic import ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.markets.base import BaseMarketsCrawler, MarketFact
from crawler.markets.fred.enums import FredField
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import MarketFeed
from models.markets.facts.fx_observation import FxObservation
from models.markets.markets_catalog import MarketsCatalog


class FredCrawler(BaseMarketsCrawler):
    """Crawl the exchange rates against the US dollar of FRED (Federal Reserve Bank of St. Louis).

    Attributes:
        URL (ClassVar[str]): The CSV export of a series.
        name (str): The crawler name.
        feed (ClassVar[MarketFeed]): FRED.
        catalogue_url (ClassVar[str]): The FRED host.
        download_delay (float): One second between two series, the `Crawl-delay` of FRED's `robots.txt`.

    Notes:
        - One CSV per currency of the catalogue: the noon buying rates in New York (H.10), daily from 1971 (1999 for
          the euro), quoted as the series is (`DEXUSEU` in dollars per euro, `DEXJPUS` in yen per dollar). Turning
          them into dollars per unit is left to `analytics.markets`.
        - The days without a rate (holidays) are empty, or `.` in the older exports: they are left out.
        - FRED data are public, no key is needed for the CSV export, and its `robots.txt` allows it.
    """

    URL: ClassVar[str] = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    name = "fred"
    feed: ClassVar[MarketFeed] = MarketFeed.FRED
    catalogue_url: ClassVar[str] = "https://fred.stlouisfed.org/"
    download_delay: float = 1.0

    def __init__(
        self,
        catalog: Optional[MarketsCatalog] = None,
        scope: Optional[CrawlScope] = None,
        crawldir: Optional[Union[str, Path]] = None,
        interval: float = 300.0,
    ) -> None:
        """Initialize the crawler.

        Args:
            catalog (Optional[MarketsCatalog]): What is read, `data/curated/markets.json` by default.
            scope (Optional[CrawlScope]): The part of the catalogue read, all of it by default.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            MarketsCatalogError: If the default catalogue cannot be loaded.
        """
        super().__init__(catalog=catalog, scope=scope, crawldir=crawldir, interval=interval)

    ############################
    # Internal Helpers Methods #
    ############################

    def _csv_url(self, series: str) -> str:
        """Build the URL of the CSV export of a series, from the first month of the scope if any.

        Args:
            series (str): The FRED series.

        Returns:
            str: The URL.
        """
        query: Dict[str, str] = {FredField.ID: series}
        if self.scope.since:
            query[FredField.START] = f"{self.scope.since}-01"
        return f"{self.URL}?{urlencode(query)}"

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the CSV of every currency series of the catalogue.

        Yields:
            Request: A request per series.
        """
        headers = self._headers("text/csv,*/*")
        self.logger.info("Requesting %d FRED exchange-rate series.", len(self.catalog.currencies))
        for entry in self.catalog.currencies:
            yield self._market_request(self._csv_url(entry.series), headers, **{FredField.SERIES: entry.series})

    def extract_facts(self, response: Response) -> Iterator[MarketFact]:
        """Extract the rates of a CSV export.

        Args:
            response (Response): The CSV.

        Returns:
            Iterator[MarketFact]: A rate per day with a value.
        """
        series = str(response.meta.get(FredField.SERIES, ""))
        rows = list(csv.reader(io.StringIO(self._body_text(response))))
        if not rows or not rows[0] or rows[0][0].strip() != FredField.DATE:
            self.logger.warning("The FRED document %s is not a CSV export.", response.url)
            return
        for row in rows[1:]:
            if len(row) < 2 or row[1].strip() in ("", "."):
                continue
            try:
                yield FxObservation(series=series, day=row[0], value=row[1], source_url=response.url)
            except ValidationError as e:
                self.logger.warning("Invalid %s rate %s left out: %s", series, row[0], e.errors()[0]["msg"])
