from __future__ import annotations

# Standard Library Imports.
import argparse
import asyncio
import sys
from datetime import UTC, datetime
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, List, Optional, Sequence

# First Party Imports.
from analytics.compounding.compounding_analysis import CompoundingAnalysis
from analytics.compounding.config_loader import CompoundingConfigLoader
from analytics.compounding.data.compounding_loader import CompoundingLoader
from analytics.compounding.doc.compounding_doc_renderer import CompoundingDocRenderer
from analytics.compounding.exception import CompoundingError
from analytics.compounding.help_loader import CompoundingHelpLoader
from conf import COMPOUNDING_DOC_PATH
from curated.exception import CuratedError
from logger import setup_logging
from models.compounding.compounding_query import CompoundingQuery
from models.compounding.compounding_report import CompoundingReport
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.data.compounding_data import CompoundingData
from models.compounding.enums import CompoundingCard, FoundationSource, Specification
from storage.exception import StorageError
from storage.storage import Storage


class CompoundingDocWriter:
    """Write the generated blocks of the service-compounding results: `uv run render-compounding-doc [--check]`.

    Attributes:
        MAIN (ClassVar[CompoundingQuery]): The analysis shown card by card.
        OTHERS (ClassVar[List[CompoundingQuery]]): The analyses summed up in the robustness block.
        config_loader (CompoundingConfigLoader): Reads `conf/analysis/compounding.yaml`.
        help_loader (CompoundingHelpLoader): Reads the `compounding` block of `conf/help.yaml`.
        logger (Logger): The writer logger.

    Notes:
        - Without option it reads the database of `CRAWLER_DATABASE_URL` once, fits the main analysis (the defaults
          of the Analysis tab) and the three others, and writes every block: run it after crawling the catalogues
          and the cloud market history.
        - `--check` writes nothing: it fails when the scope block is out of date with the configuration, or a block
          marker is missing (for the CI and the tests, no database needed).
    """

    MAIN: ClassVar[CompoundingQuery] = CompoundingQuery()
    OTHERS: ClassVar[List[CompoundingQuery]] = [
        CompoundingQuery(source=FoundationSource.DATA_DRIVEN),
        CompoundingQuery(specification=Specification.SHARE),
        CompoundingQuery(specification=Specification.SHARE, source=FoundationSource.DATA_DRIVEN),
    ]

    def __init__(
        self,
        config_loader: Optional[CompoundingConfigLoader] = None,
        help_loader: Optional[CompoundingHelpLoader] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the writer.

        Args:
            config_loader (Optional[CompoundingConfigLoader]): Reads the configuration.
            help_loader (Optional[CompoundingHelpLoader]): Reads the help texts.
            logger (Optional[Logger]): The writer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.config_loader = config_loader if config_loader else CompoundingConfigLoader(self.logger)
        self.help_loader = help_loader if help_loader else CompoundingHelpLoader(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _arguments(self, argv: Optional[Sequence[str]]) -> argparse.Namespace:
        """Read the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            argparse.Namespace: The document and whether to only check it.
        """
        parser = argparse.ArgumentParser(
            prog="render-compounding-doc",
            description="Write the generated blocks of docs/analysis/service-capability-compounding-results.md.",
        )
        parser.add_argument("--output", type=Path, default=COMPOUNDING_DOC_PATH, help="The document to write.")
        parser.add_argument("--check", action="store_true", help="Only check the scope block and the markers.")
        return parser.parse_args(argv)

    async def _data(self, config: CompoundingConfig) -> CompoundingData:
        """Read what the models fit.

        Args:
            config (CompoundingConfig): The scope of the analysis.

        Returns:
            CompoundingData: The dated catalogues, the shares and the market sizes.

        Raises:
            StorageError: If the database cannot be read.
            CuratedError: If the chronology cannot be read.
        """
        async with Storage() as storage:
            chronology = await storage.catalogs.chronology()
            return await CompoundingLoader(config, chronology, self.logger).load(storage)

    ############################
    # Publicly Exposed Methods #
    ############################

    def render(self, current: str, results: bool = True) -> str:
        """Print the document with its generated blocks.

        Args:
            current (str): The document as it stands.
            results (bool): Whether to compute the results from the database (else only the scope block).

        Returns:
            str: The document.

        Raises:
            CompoundingError: If the configuration or the help texts cannot be read.
            StorageError: If the database cannot be read.
            CuratedError: If the chronology cannot be read.
        """
        config = self.config_loader.load()
        renderer = CompoundingDocRenderer(self.help_loader.load(), self.logger)
        text = renderer.splice(current, CompoundingDocRenderer.SCOPE, renderer.foundations(config))
        if not results:
            return text
        data = asyncio.run(self._data(config))
        analysis = CompoundingAnalysis(config, self.logger)
        main: CompoundingReport = analysis.run(self.MAIN, data)
        text = renderer.splice(text, CompoundingDocRenderer.RUN, renderer.run_stamp(main, datetime.now(UTC).date()))
        for card in CompoundingCard:
            text = renderer.splice(text, card.value, renderer.card(card, main))
        others = [analysis.run(query, data) for query in self.OTHERS]
        return renderer.splice(text, CompoundingDocRenderer.ROBUSTNESS, renderer.robustness(others))

    def missing(self, text: str) -> List[str]:
        """List the blocks whose markers are missing.

        Args:
            text (str): The document.

        Returns:
            List[str]: The block names without both markers.
        """
        renderer = CompoundingDocRenderer(self.help_loader.load(), self.logger)
        return [
            name
            for name in renderer.names()
            if renderer.START.format(name=name) not in text or renderer.END.format(name=name) not in text
        ]

    def parse(self, argv: Optional[Sequence[str]] = None) -> int:
        """Run the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            int: The exit code: 0 on success, 1 when a file or the database fails, or the document is out of date
                (logged).
        """
        arguments = self._arguments(argv)
        output: Path = arguments.output
        current = output.read_text(encoding="utf-8") if output.is_file() else ""
        try:
            text = self.render(current, results=not arguments.check)
            missing = self.missing(current)
        except CompoundingError as e:
            self.logger.error("%s", e)
            return 1
        except CuratedError as e:
            self.logger.error("The chronology cannot be read: %s", e)
            return 1
        except StorageError as e:
            self.logger.error("The database cannot be read: %s", e)
            return 1
        if missing:
            self.logger.error("%s misses the markers of the blocks %s.", output, ", ".join(missing))
            return 1
        if arguments.check:
            if current != text:
                self.logger.error("%s is out of date: run `uv run render-compounding-doc`.", output)
                return 1
            self.logger.info("%s is up to date.", output)
            return 0
        output.write_text(text, encoding="utf-8")
        self.logger.info("Compounding results written to %s (%d lines).", output, len(text.splitlines()))
        return 0


def main() -> int:
    """Console entry point of `uv run render-compounding-doc`.

    Returns:
        int: The exit code.
    """
    setup_logging()
    return CompoundingDocWriter().parse(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
