from __future__ import annotations

# Standard Library Imports.
import argparse
import asyncio
import sys
from datetime import UTC, date, datetime
from logging import Logger, getLogger
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

# First Party Imports.
from analytics.companies.companies_doc_renderer import CompaniesDocRenderer
from conf import COMPANIES_DOC_PATH
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.exception import CuratedError
from logger import setup_logging
from storage.exception import StorageError
from storage.storage import Storage


class CompaniesDocWriter:
    """Write the generated blocks of the companies guide: `uv run render-companies-doc [--coverage]`.

    Attributes:
        catalogs (BundleCatalogs): Reads the companies, the listings and the chronology from the bundle.
        renderer (CompaniesDocRenderer): Prints the blocks.
        logger (Logger): The writer logger.

    Notes:
        - The catalogue block follows the bundle (`data/curated/companies.json`): `--check` writes nothing and
          fails when it is out of date (for the CI and the tests).
        - `--coverage` also prints the span of the stored series, read from the database of `CRAWLER_DATABASE_URL`:
          run it after a companies crawl.
    """

    def __init__(
        self,
        catalogs: Optional[BundleCatalogs] = None,
        renderer: Optional[CompaniesDocRenderer] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the writer.

        Args:
            catalogs (Optional[BundleCatalogs]): Reads the catalogues, `data/curated` by default.
            renderer (Optional[CompaniesDocRenderer]): Prints the blocks.
            logger (Optional[Logger]): The writer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.catalogs = catalogs if catalogs else BundleCatalogs(logger=self.logger)
        self.renderer = renderer if renderer else CompaniesDocRenderer(self.logger)

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
            prog="render-companies-doc",
            description="Print the generated blocks of docs/analysis/company-financials-and-rd.md.",
        )
        parser.add_argument("--output", type=Path, default=COMPANIES_DOC_PATH, help="The guide to write.")
        parser.add_argument("--check", action="store_true", help="Only check that the catalogue block is up to date.")
        parser.add_argument("--coverage", action="store_true", help="Also print the span of the stored series.")
        return parser.parse_args(argv)

    async def _spans(self) -> Dict[Tuple[str, str, str], Tuple[date, date, int]]:
        """Read the span of the stored series.

        Returns:
            Dict[Tuple[str, str, str], Tuple[date, date, int]]: The first and last period ends and the points, by
                company, indicator and granularity.

        Raises:
            StorageError: If the database cannot be read.
        """
        async with Storage() as storage:
            return await storage.indicators.coverage()

    ############################
    # Publicly Exposed Methods #
    ############################

    def render(self, current: str, coverage: bool = False) -> str:
        """Print the guide with its generated blocks.

        Args:
            current (str): The guide as it stands.
            coverage (bool): Whether to print the span of the stored series too.

        Returns:
            str: The guide.

        Raises:
            CuratedError: If a catalogue cannot be read from the bundle.
            StorageError: If the coverage cannot be read.
        """
        catalog, chronology, markets = self.catalogs.companies(), self.catalogs.chronology(), self.catalogs.markets()
        block = self.renderer.catalogue(catalog, chronology, markets)
        text = self.renderer.splice(current, CompaniesDocRenderer.CATALOGUE, block)
        if coverage:
            spans = asyncio.run(self._spans())
            text = self.renderer.splice(
                text, CompaniesDocRenderer.COVERAGE, self.renderer.coverage(catalog, spans, datetime.now(UTC).date())
            )
        return text

    def parse(self, argv: Optional[Sequence[str]] = None) -> int:
        """Run the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            int: The exit code: 0 on success, 1 when a catalogue or the database fails, or the guide is out of
                date (logged).
        """
        arguments = self._arguments(argv)
        output: Path = arguments.output
        current = output.read_text(encoding="utf-8") if output.is_file() else ""
        try:
            text = self.render(current, coverage=arguments.coverage and not arguments.check)
        except CuratedError as e:
            self.logger.error("%s", e)
            return 1
        except StorageError as e:
            self.logger.error("The coverage cannot be read: %s", e)
            return 1
        if arguments.check:
            if current != text:
                self.logger.error("%s is out of date: run `uv run render-companies-doc`.", output)
                return 1
            self.logger.info("%s is up to date.", output)
            return 0
        output.write_text(text, encoding="utf-8")
        self.logger.info("Companies guide written to %s (%d lines).", output, len(text.splitlines()))
        return 0


def main() -> int:
    """Console entry point of `uv run render-companies-doc`.

    Returns:
        int: The exit code.
    """
    setup_logging()
    return CompaniesDocWriter().parse(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
