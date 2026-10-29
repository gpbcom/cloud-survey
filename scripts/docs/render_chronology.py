from __future__ import annotations

# Standard Library Imports.
import argparse
import sys
from logging import Logger, getLogger
from pathlib import Path
from typing import Optional, Sequence

# First Party Imports.
from analytics.history.chronology_renderer import ChronologyRenderer
from conf import CHRONOLOGY_DOC_PATH, CURATED_DIR
from curated.bundle.bundle_catalogs import BundleCatalogs
from curated.bundle.bundle_files import BundleFiles
from curated.exception import CuratedError
from logger import setup_logging


class ChronologyDocWriter:
    """Write the chronology guide from the chronology: `uv run render-chronology`.

    Attributes:
        renderer (ChronologyRenderer): Prints it as Markdown.
        logger (Logger): The writer logger.

    Notes:
        - The chronology is read from the bundle (`data/curated/chronology.json`), the reviewed copy: run
          `uv run curated export` first to print the edits made in the explorer.
        - `--check` writes nothing and fails when the guide is not what the chronology prints (for the CI).
    """

    def __init__(self, renderer: Optional[ChronologyRenderer] = None, logger: Optional[Logger] = None) -> None:
        """Initialize the writer.

        Args:
            renderer (Optional[ChronologyRenderer]): Prints it as Markdown.
            logger (Optional[Logger]): The writer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.renderer = renderer if renderer else ChronologyRenderer(logger=self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _arguments(self, argv: Optional[Sequence[str]]) -> argparse.Namespace:
        """Read the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            argparse.Namespace: The chronology, the guide and whether to only check it.
        """
        parser = argparse.ArgumentParser(
            prog="render-chronology",
            description="Print the computing chronology as docs/analysis/leaders-chronology.md.",
        )
        parser.add_argument("--bundle", type=Path, default=CURATED_DIR, help="The curated bundle directory.")
        parser.add_argument("--output", type=Path, default=CHRONOLOGY_DOC_PATH, help="The guide to write.")
        parser.add_argument("--check", action="store_true", help="Only check that the guide is up to date.")
        return parser.parse_args(argv)

    ############################
    # Publicly Exposed Methods #
    ############################

    def render(self, bundle: Path = CURATED_DIR) -> str:
        """Print the chronology.

        Args:
            bundle (Path): The curated bundle directory.

        Returns:
            str: The guide.

        Raises:
            CuratedError: If the chronology cannot be read from the bundle.
        """
        catalogs = BundleCatalogs(BundleFiles(bundle, self.logger), logger=self.logger)
        return self.renderer.markdown(catalogs.chronology())

    def parse(self, argv: Optional[Sequence[str]] = None) -> int:
        """Run the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            int: The exit code: 0 on success, 1 when the chronology is invalid or the guide is out of date (logged).
        """
        arguments = self._arguments(argv)
        try:
            text = self.render(arguments.bundle)
        except CuratedError as e:
            self.logger.error("%s", e)
            return 1
        output: Path = arguments.output
        if arguments.check:
            current = output.read_text(encoding="utf-8") if output.is_file() else ""
            if current != text:
                self.logger.error("%s is out of date: run `uv run render-chronology`.", output)
                return 1
            self.logger.info("%s is up to date.", output)
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        self.logger.info("Chronology guide written to %s (%d lines).", output, len(text.splitlines()))
        return 0


def main() -> int:
    """Console entry point of `uv run render-chronology`.

    Returns:
        int: The exit code.
    """
    setup_logging()
    return ChronologyDocWriter().parse(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
