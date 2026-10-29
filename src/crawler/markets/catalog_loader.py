from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Dict, Optional

# Third Party Imports.
import yaml
from pydantic import JsonValue, ValidationError

# First Party Imports.
from conf import HELP_PATH
from crawler.exception import MarketsCatalogError
from models.markets.enums import MarketControl
from models.markets.help.markets_help import MarketsHelp


class MarketsCatalogLoader:
    """Load the tooltips of the markets cards (the `markets` block of `conf/help.yaml`).

    Attributes:
        HELP_BLOCK (ClassVar[str]): The block of `conf/help.yaml` holding the markets tooltips.
        logger (Logger): The loader logger.

    Notes:
        The markets catalogue is a curated catalogue, read from the database (`storage.catalogs`) or the bundle
        (`BundleCatalogs`), with its crawler settings (the `markets` block of `conf/settings.yaml`).
    """

    HELP_BLOCK: ClassVar[str] = "markets"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _document(self, path: Path) -> Dict[str, JsonValue]:
        """Read a YAML file as a mapping.

        Args:
            path (Path): The file.

        Returns:
            Dict[str, JsonValue]: Its content, empty for an empty file.

        Raises:
            MarketsCatalogError: If the file cannot be read, is not valid YAML or is not a mapping.
        """
        try:
            with path.open(encoding="utf-8") as file:
                content = yaml.safe_load(file) or {}
        except OSError as e:
            self.logger.error("The markets catalogue %s cannot be read: %s", path, e.strerror)
            raise MarketsCatalogError(str(path), f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The markets catalogue %s is not valid YAML.", path)
            raise MarketsCatalogError(str(path), f"the file is not valid YAML.\n{e}") from e
        if not isinstance(content, dict):
            self.logger.error("The markets catalogue %s is not a mapping.", path)
            raise MarketsCatalogError(str(path), "the file is not a mapping.")
        return content

    def _block(self, path: Path, block: str) -> Dict[str, JsonValue]:
        """Read one block of a YAML file of blocks (`conf/settings.yaml`, `conf/help.yaml`).

        Args:
            path (Path): The file.
            block (str): The block.

        Returns:
            Dict[str, JsonValue]: The content of the block.

        Raises:
            MarketsCatalogError: If the file cannot be read or has no such block.
        """
        content = self._document(path).get(block)
        if not isinstance(content, dict):
            self.logger.error("The file %s has no %s block.", path, block)
            raise MarketsCatalogError(str(path), f"the file has no `{block}` block.")
        return content

    def _validate(self, path: Path, content: Dict[str, JsonValue]) -> MarketsHelp:
        """Validate the explanations.

        Args:
            path (Path): The file (named in the errors).
            content (Dict[str, JsonValue]): The content of its block.

        Returns:
            MarketsHelp: The validated explanations.

        Raises:
            MarketsCatalogError: If the content is invalid.
        """
        try:
            return MarketsHelp.model_validate(content)
        except ValidationError as e:
            self.logger.error("The markets explanations %s are invalid (%d errors).", path, e.error_count())
            raise MarketsCatalogError(str(path), f"the content is invalid.\n{e}") from e

    ############################
    # Publicly Exposed Methods #
    ############################

    def help(self, path: Path = HELP_PATH) -> MarketsHelp:
        """Read the tooltips of the markets cards.

        Args:
            path (Path): The help file, whose `markets` block holds the explanations.

        Returns:
            MarketsHelp: The explanation of each control and choice, and the correlation method.

        Raises:
            MarketsCatalogError: If the file cannot be read or is invalid.
        """
        explanations = self._validate(path, self._block(path, self.HELP_BLOCK))
        missing = [control.value for control in MarketControl if explanations.control(control) is None]
        if missing:
            self.logger.warning("The markets explanations %s miss: %s.", path, ", ".join(missing))
        self.logger.debug(
            "Markets explanations loaded: %d controls, %d choices.",
            len(explanations.controls),
            len(explanations.options),
        )
        return explanations
