from __future__ import annotations

# Standard Library Imports.
import argparse
import asyncio
import sys
from collections import defaultdict
from datetime import UTC, date, datetime
from logging import Logger, getLogger
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from analytics.markets.markets_doc_renderer import MarketsDocRenderer
from conf import MARKETS_DOC_PATH
from crawler.exception import MarketsCatalogError
from crawler.markets.catalog_loader import MarketsCatalogLoader
from logger import setup_logging
from storage.exception import StorageError
from storage.storage import Storage


class MarketsDocWriter:
    """Write the generated blocks of the markets guide: `uv run render-markets-doc [--coverage]`.

    Attributes:
        loader (MarketsCatalogLoader): Reads `conf/history/markets.yaml` and the chronology.
        renderer (MarketsDocRenderer): Prints the blocks.
        logger (Logger): The writer logger.

    Notes:
        - The catalogue block follows the YAML: `--check` writes nothing and fails when it is out of date (for the
          CI and the tests).
        - `--coverage` also prints the coverage of the stored series, read from the database of
          `CRAWLER_DATABASE_URL`: run it after a markets crawl.
    """

    def __init__(
        self,
        loader: Optional[MarketsCatalogLoader] = None,
        renderer: Optional[MarketsDocRenderer] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the writer.

        Args:
            loader (Optional[MarketsCatalogLoader]): Reads the catalogue and the chronology.
            renderer (Optional[MarketsDocRenderer]): Prints the blocks.
            logger (Optional[Logger]): The writer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.loader = loader if loader else MarketsCatalogLoader(self.logger)
        self.renderer = renderer if renderer else MarketsDocRenderer(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _arguments(self, argv: Optional[Sequence[str]]) -> argparse.Namespace:
        """Read the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            argparse.Namespace: The guide, whether to only check it and whether to print the coverage.
        """
        parser = argparse.ArgumentParser(
            prog="render-markets-doc",
            description="Print the generated blocks of docs/analysis/market-shares-and-stocks.md.",
        )
        parser.add_argument("--output", type=Path, default=MARKETS_DOC_PATH, help="The guide to write.")
        parser.add_argument("--check", action="store_true", help="Only check that the catalogue block is up to date.")
        parser.add_argument("--coverage", action="store_true", help="Also print the coverage of the stored series.")
        return parser.parse_args(argv)

    async def _coverage(
        self,
    ) -> Tuple[Dict[Tuple[str, str, str], List[date]], Dict[str, List[date]], Dict[Tuple[str, str, str], List[date]]]:
        """Read the periods with figures of the stored series.

        Returns:
            Tuple[Dict[Tuple[str, str, str], List[date]], Dict[str, List[date]], Dict[Tuple[str, str, str],
                List[date]]]: The months of each monthly share series, the months with a close of each listing, and
                the quarters of each quarterly share series.

        Raises:
            StorageError: If the database cannot be read.
        """
        async with Storage() as storage:
            shares = await storage.shares.months()
            quarters = await storage.shares.quarters()
            listings: Dict[str, List[date]] = defaultdict(list)
            for point in await storage.stocks.read():
                month = point.day.replace(day=1)
                if not listings[point.listing] or listings[point.listing][-1] != month:
                    listings[point.listing].append(month)
        return shares, dict(listings), quarters

    ############################
    # Publicly Exposed Methods #
    ############################

    def render(self, current: str, coverage: bool = False) -> str:
        """Print the guide with its generated blocks.

        Args:
            current (str): The guide as it stands.
            coverage (bool): Whether to print the coverage of the stored series too.

        Returns:
            str: The guide.

        Raises:
            MarketsCatalogError: If the catalogue cannot be loaded.
            StorageError: If the coverage cannot be read.
        """
        catalog, chronology = self.loader.load(), self.loader.chronology()
        text = self.renderer.splice(current, MarketsDocRenderer.CATALOGUE, self.renderer.catalogue(catalog, chronology))
        if coverage:
            shares, listings, quarters = asyncio.run(self._coverage())
            block = self.renderer.coverage(shares, listings, datetime.now(UTC).date(), quarters)
            text = self.renderer.splice(text, MarketsDocRenderer.COVERAGE, block)
        return text

    def parse(self, argv: Optional[Sequence[str]] = None) -> int:
        """Run the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            int: The exit code: 0 on success, 1 when the catalogue or the database fails, or the guide is out of
                date (logged).
        """
        arguments = self._arguments(argv)
        output: Path = arguments.output
        current = output.read_text(encoding="utf-8") if output.is_file() else ""
        try:
            text = self.render(current, coverage=arguments.coverage and not arguments.check)
        except MarketsCatalogError as e:
            self.logger.error("%s", e)
            return 1
        except StorageError as e:
            self.logger.error("The coverage cannot be read: %s", e)
            return 1
        if arguments.check:
            if current != text:
                self.logger.error("%s is out of date: run `uv run render-markets-doc`.", output)
                return 1
            self.logger.info("%s is up to date.", output)
            return 0
        output.write_text(text, encoding="utf-8")
        self.logger.info("Markets guide written to %s (%d lines).", output, len(text.splitlines()))
        return 0


def main() -> int:
    """Console entry point of `uv run render-markets-doc`.

    Returns:
        int: The exit code.
    """
    setup_logging()
    return MarketsDocWriter().parse(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
