from __future__ import annotations

# Standard Library Imports.
import csv
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import AsyncGenerator, ClassVar, Iterator, List, Optional, Union
from urllib.parse import urlencode

# Third Party Imports.
from pydantic import ValidationError
from scrapling.spiders import Request, Response

# First Party Imports.
from crawler.markets.base import BaseMarketsCrawler, MarketFact
from crawler.markets.statcounter.enums import StatCounterDevice, StatCounterMeta, StatCounterParameter
from models.markets.catalog.share_segment import ShareSegment
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import AreaKind, Device, MarketFeed
from models.markets.facts.share_observation import ShareObservation
from models.markets.markets_catalog import MarketsCatalog


class StatCounterCrawler(BaseMarketsCrawler):
    """Crawl the monthly usage shares of StatCounter Global Stats (search, browsers, OS, vendors, AI chatbots).

    Attributes:
        URL (ClassVar[str]): The CSV export of a chart.
        DATE_COLUMN (ClassVar[str]): The header of the month column.
        name (str): The crawler name.
        feed (ClassVar[MarketFeed]): StatCounter.
        catalogue_url (ClassVar[str]): The StatCounter host.
        download_delay (float): Two seconds between two CSV, a polite pace for a free service.

    Notes:
        - One CSV per area, statistic and device, from the first month of the catalogue (or of the crawl scope) to
          the current month: the months in rows, the labels in columns, the shares in percent of the page views.
        - The export appends all-zero rows for the months before the one asked for: they are left out, as the
          zero shares (a label not yet or no longer seen).
        - StatCounter has no `robots.txt` and its data are free to reuse with attribution (CC BY-SA 3.0).
    """

    URL: ClassVar[str] = "https://gs.statcounter.com/chart.php"
    DATE_COLUMN: ClassVar[str] = "Date"
    name = "statcounter"
    feed: ClassVar[MarketFeed] = MarketFeed.STATCOUNTER
    catalogue_url: ClassVar[str] = "https://gs.statcounter.com/"
    download_delay: float = 2.0

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

    def _areas(self) -> List[str]:
        """Get the areas read: those of the scope, or every area of the catalogue but the unions.

        Returns:
            List[str]: The StatCounter regions.
        """
        areas = [area.key for area in self.catalog.areas if area.kind is not AreaKind.UNION]
        if not self.scope.areas:
            return areas
        unknown = [key for key in self.scope.areas if key not in areas]
        if unknown:
            self.logger.warning("Areas left out (unknown or a union): %s.", ", ".join(unknown))
        return [key for key in areas if key in self.scope.areas]

    def _first_month(self, segment: ShareSegment) -> str:
        """Get the first month read for a segment: the latest of the catalogue's, the segment's and the scope's.

        Args:
            segment (ShareSegment): The segment.

        Returns:
            str: The month, `YYYY-MM`.
        """
        return max(month for month in (self.catalog.statcounter_from, segment.first_month, self.scope.since) if month)

    def _csv_url(self, segment: ShareSegment, area: str, device: Device, first: str, last: str) -> str:
        """Build the URL of a CSV export.

        Args:
            segment (ShareSegment): The segment (its statistic).
            area (str): The region.
            device (Device): The devices.
            first (str): The first month, `YYYY-MM`.
            last (str): The last month, `YYYY-MM`.

        Returns:
            str: The URL.
        """
        query = {
            StatCounterParameter.DEVICE.value: StatCounterDevice[device.name].value,
            StatCounterParameter.STAT.value: segment.stat.value if segment.stat else "",
            StatCounterParameter.REGION.value: area,
            StatCounterParameter.GRANULARITY.value: "monthly",
            StatCounterParameter.FROM.value: first.replace("-", ""),
            StatCounterParameter.TO.value: last.replace("-", ""),
            StatCounterParameter.CSV.value: "1",
        }
        return f"{self.URL}?{urlencode(query)}"

    def _share(self, raw: str) -> Optional[float]:
        """Read a share cell.

        Args:
            raw (str): The cell.

        Returns:
            Optional[float]: The share, `None` when empty, unreadable or zero.
        """
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if value > 0 else None

    ############################
    # Publicly Exposed Methods #
    ############################

    async def start_requests(self) -> AsyncGenerator[Request]:
        """Request the CSV of every area, StatCounter segment and device of the catalogue.

        Yields:
            Request: A request per area, statistic and device.
        """
        last = datetime.now(UTC).strftime("%Y-%m")
        headers = self._headers("text/csv,*/*")
        segments = self.catalog.statcounter_segments()
        areas = self._areas()
        self.logger.info("Requesting %d areas x %d StatCounter segments.", len(areas), len(segments))
        for area in areas:
            for segment in segments:
                first = self._first_month(segment)
                for device in segment.devices:
                    yield self._market_request(
                        self._csv_url(segment, area, device, first, last),
                        headers,
                        **{
                            StatCounterMeta.STAT: segment.stat.value if segment.stat else "",
                            StatCounterMeta.AREA: area,
                            StatCounterMeta.DEVICE: device.value,
                            StatCounterMeta.FROM: first,
                        },
                    )

    def extract_facts(self, response: Response) -> Iterator[MarketFact]:
        """Extract the shares of a CSV export.

        Args:
            response (Response): The CSV.

        Returns:
            Iterator[MarketFact]: A share per month and label, the zero ones and the padding months left out.
        """
        rows = list(csv.reader(io.StringIO(self._body_text(response))))
        if not rows or not rows[0] or rows[0][0].strip() != self.DATE_COLUMN:
            self.logger.warning("The StatCounter document %s is not a CSV export.", response.url)
            return
        labels = [label.strip() for label in rows[0][1:]]
        first = str(response.meta.get(StatCounterMeta.FROM, ""))
        for row in rows[1:]:
            if not row or row[0].strip() < first:
                continue
            for label, raw in zip(labels, row[1:], strict=False):
                value = self._share(raw)
                if value is None or not label:
                    continue
                try:
                    yield ShareObservation(
                        stat=response.meta.get(StatCounterMeta.STAT),
                        area=response.meta.get(StatCounterMeta.AREA),
                        device=response.meta.get(StatCounterMeta.DEVICE),
                        month=row[0],
                        label=label,
                        value=value,
                        source_url=response.url,
                    )
                except ValidationError as e:
                    self.logger.warning(
                        "Invalid StatCounter share %s %s in %s: %s", row[0], label, response.url, e.errors()[0]["msg"]
                    )
