from __future__ import annotations

# Standard Library Imports.
from datetime import date
from pathlib import Path
from typing import ClassVar, Iterator, List, Optional, Sequence, Tuple, Union

# Third Party Imports.
from pydantic import ValidationError

# First Party Imports.
from crawler.markets.base import BaseMarketsCrawler, MarketFact
from crawler.markets.press.sentence_reader import PressSentenceReader
from crawler.markets.press.table_reader import PressTableReader, TableShare
from models.markets.crawl_scope import CrawlScope
from models.markets.enums import Granularity, ShareSource
from models.markets.facts.release_share import ReleaseShare
from models.markets.markets_catalog import MarketsCatalog
from models.markets.press.period_label import PeriodLabel
from models.markets.press.press_family import PressFamily


class BasePressCrawler(BaseMarketsCrawler):
    """Base class for the crawlers of the market shares analysts publish in their press releases (phase 2).

    Attributes:
        share_source (ClassVar[ShareSource]): The firm crawled.
        tables (PressTableReader): Reads the share tables of a release.
        sentences (PressSentenceReader): Reads the shares a release states in its sentences.
        periods (PeriodLabel): Reads the period of a release title.

    Notes:
        - A release is read when its title (and the caption of its table) matches a family of the catalogue
          (`press` in `data/curated/markets.json`), which gives its segment and its area.
        - Its tables are read first: a release with a share table gives every company of every period column. A
          release without (TrendForce) gives the shares its sentences state, for the companies the catalogue names.
        - The shares are streamed as stated, the label as printed: mapping them to the companies is left to
          `analytics.markets`.
    """

    share_source: ClassVar[ShareSource] = ShareSource.IDC

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
            scope (Optional[CrawlScope]): The part read: the releases published since `scope.since` only.
            crawldir (Optional[Union[str, Path]]): Directory for checkpoint files, enabling pause/resume.
            interval (float): Seconds between periodic checkpoint saves.

        Raises:
            MarketsCatalogError: If the default catalogue cannot be loaded.
        """
        super().__init__(catalog=catalog, scope=scope, crawldir=crawldir, interval=interval)
        self.tables = PressTableReader(self.logger)
        self.sentences = PressSentenceReader(self.logger)
        self.periods = PeriodLabel()

    ############################
    # Internal Helpers Methods #
    ############################

    def _families(self) -> List[PressFamily]:
        """Get the families of releases of the firm.

        Returns:
            List[PressFamily]: The families, in the catalogue order.
        """
        return self.catalog.press_families(self.share_source)

    def _family(self, title: str, caption: str = "") -> Optional[Tuple[int, PressFamily]]:
        """Find the family of a release.

        Args:
            title (str): The release title.
            caption (str): The caption of its table, if any.

        Returns:
            Optional[Tuple[int, PressFamily]]: The index and the first family it matches, `None` when it matches none.

        Notes:
            The caption says best what a table holds ("Top Five Tablet Companies, Worldwide Shipments" in a release on
            tablets and Chromebooks): it is matched alone first, then with the title when it names no product
            ("Worldwide Shipments").
        """
        families = list(enumerate(self._families()))
        by_caption = (
            next(((index, family) for index, family in families if family.matches(caption)), None) if caption else None
        )
        if by_caption is not None:
            return by_caption
        text = f"{title} | {caption}"
        return next(((index, family) for index, family in families if family.matches(text)), None)

    def _names(self) -> List[str]:
        """Get the company names the firm writes: its labels in the catalogue, and the unmapped companies.

        Returns:
            List[str]: The names.
        """
        mapped = [entry.label for entry in self.catalog.labels if entry.source is self.share_source]
        return [*mapped, *self.catalog.press_names]

    def _since(self) -> Optional[date]:
        """Get the first publication day read.

        Returns:
            Optional[date]: The first day of `scope.since`, `None` to read every release.
        """
        return date.fromisoformat(f"{self.scope.since}-01") if self.scope.since else None

    def _release_shares(
        self, family: PressFamily, shares: Sequence[TableShare], title: str, published: date, url: str
    ) -> Iterator[MarketFact]:
        """Build the facts of the shares a release states.

        Args:
            family (PressFamily): The family of the release.
            shares (Sequence[TableShare]): The company, period, granularity and share of each.
            title (str): The release title.
            published (date): When it was published.
            url (str): The release.

        Returns:
            Iterator[MarketFact]: The valid shares (an invalid one is logged and left out).
        """
        for label, period, granularity, value in shares:
            try:
                yield ReleaseShare(
                    source=self.share_source,
                    segment=family.segment,
                    area=family.area,
                    period=period,
                    granularity=granularity,
                    label=label,
                    value=value,
                    title=title,
                    published=published,
                    source_url=url,
                )
            except ValidationError as e:
                self.logger.warning("Invalid %s share of %s in %s: %s", self.name, label, url, e.errors()[0]["msg"])

    def _read_release(
        self, family: PressFamily, body: str, text: str, title: str, published: date, url: str
    ) -> Iterator[MarketFact]:
        """Read the shares of a release: its tables of the family, else its sentences.

        Args:
            family (PressFamily): The family the title matched.
            body (str): The HTML of the release body.
            text (str): The text of the release body.
            title (str): The release title.
            published (date): When it was published.
            url (str): The release.

        Returns:
            Iterator[MarketFact]: The shares stated.
        """
        tables = [
            shares for caption, shares in self.tables.read(body) if self._family(title, caption) == self._family(title)
        ]
        if tables:
            for shares in tables:
                yield from self._release_shares(family, shares, title, published, url)
            return
        period: Optional[Tuple[date, Granularity]] = self.periods.release(title, published)
        if period is None:
            self.logger.warning("The %s release %s states no period in its title: left out.", self.name, url)
            return
        shares = self.sentences.read(text, self._names(), period)
        if not shares:
            self.logger.info("The %s release %s states no company share.", self.name, url)
        yield from self._release_shares(family, shares, title, published, url)
