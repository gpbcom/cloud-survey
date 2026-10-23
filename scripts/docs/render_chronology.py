from __future__ import annotations

# Standard Library Imports.
import argparse
import sys
from logging import Logger, getLogger
from pathlib import Path
from typing import Optional, Sequence

# First Party Imports.
from analytics.history.chronology_loader import ChronologyLoader
from analytics.history.chronology_renderer import ChronologyRenderer
from analytics.history.exception import ChronologyFileError
from conf import CHRONOLOGY_DOC_PATH, CHRONOLOGY_PATH
from logger import setup_logging


class ChronologyDocWriter:
    """Write the chronology guide from the chronology: `uv run render-chronology`.

    Attributes:
        loader (ChronologyLoader): Reads `conf/history/chronology.yaml`.
        renderer (ChronologyRenderer): Prints it as Markdown.
        logger (Logger): The writer logger.

    Notes:
        `--check` writes nothing and fails when the guide is not what the chronology prints (for the CI).
    """

    def __init__(
        self,
        loader: Optional[ChronologyLoader] = None,
        renderer: Optional[ChronologyRenderer] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the writer.

        Args:
            loader (Optional[ChronologyLoader]): Reads the chronology.
            renderer (Optional[ChronologyRenderer]): Prints it as Markdown.
            logger (Optional[Logger]): The writer logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.loader = loader if loader else ChronologyLoader(self.logger)
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
        parser.add_argument("--source", type=Path, default=CHRONOLOGY_PATH, help="The chronology YAML.")
        parser.add_argument("--output", type=Path, default=CHRONOLOGY_DOC_PATH, help="The guide to write.")
        parser.add_argument("--check", action="store_true", help="Only check that the guide is up to date.")
        return parser.parse_args(argv)

    ############################
    # Publicly Exposed Methods #
    ############################

    def render(self, source: Path = CHRONOLOGY_PATH) -> str:
        """Print the chronology.

        Args:
            source (Path): The chronology YAML.

        Returns:
            str: The guide.

        Raises:
            ChronologyFileError: If the chronology cannot be loaded.
        """
        return self.renderer.markdown(self.loader.load(source))

    def parse(self, argv: Optional[Sequence[str]] = None) -> int:
        """Run the command line.

        Args:
            argv (Optional[Sequence[str]]): The arguments, those of the process by default.

        Returns:
            int: The exit code: 0 on success, 1 when the chronology is invalid or the guide is out of date (logged).
        """
        arguments = self._arguments(argv)
        try:
            text = self.render(arguments.source)
        except ChronologyFileError as e:
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
