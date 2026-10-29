from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Dict, Optional

# Third Party Imports.
import yaml
from pydantic import JsonValue, ValidationError

# First Party Imports.
from conf import HELP_PATH, SETTINGS_PATH
from crawler.exception import CompaniesCatalogError
from models.companies.concepts.financial_concepts import FinancialConcepts
from models.companies.help.financials_help import FinancialsHelp


class CompaniesCatalogLoader:
    """Load how the companies' statement lines are mapped, and the tooltips of the company financials card.

    Attributes:
        CONCEPTS_BLOCK (ClassVar[str]): The block of `conf/settings.yaml` holding the statement mapping.
        HELP_BLOCK (ClassVar[str]): The block of `conf/help.yaml` holding the company financials tooltips.
        logger (Logger): The loader logger.

    Notes:
        - The mapping is the `concepts` block of `conf/settings.yaml`, the tooltips the `financials` block of
          `conf/help.yaml`.
        - The companies crawled and the figures researched by hand are curated catalogues, read from the database
          (`storage.catalogs`) or the bundle (`BundleCatalogs`).
    """

    CONCEPTS_BLOCK: ClassVar[str] = "concepts"
    HELP_BLOCK: ClassVar[str] = "financials"

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
            CompaniesCatalogError: If the file cannot be read, is not valid YAML or is not a mapping.
        """
        try:
            with path.open(encoding="utf-8") as file:
                content = yaml.safe_load(file) or {}
        except OSError as e:
            self.logger.error("The companies catalogue %s cannot be read: %s", path, e.strerror)
            raise CompaniesCatalogError(str(path), f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The companies catalogue %s is not valid YAML.", path)
            raise CompaniesCatalogError(str(path), f"the file is not valid YAML.\n{e}") from e
        if not isinstance(content, dict):
            self.logger.error("The companies catalogue %s is not a mapping.", path)
            raise CompaniesCatalogError(str(path), "the file is not a mapping.")
        return content

    def _block(self, path: Path, block: str) -> Dict[str, JsonValue]:
        """Read one block of a YAML file of blocks (`conf/settings.yaml`, `conf/help.yaml`).

        Args:
            path (Path): The file.
            block (str): The block.

        Returns:
            Dict[str, JsonValue]: The content of the block.

        Raises:
            CompaniesCatalogError: If the file cannot be read or has no such block.
        """
        content = self._document(path).get(block)
        if not isinstance(content, dict):
            self.logger.error("The file %s has no %s block.", path, block)
            raise CompaniesCatalogError(str(path), f"the file has no `{block}` block.")
        return content

    def _validate[Model: (FinancialConcepts, FinancialsHelp)](
        self, path: Path, content: Dict[str, JsonValue], model: type[Model]
    ) -> Model:
        """Validate the content of a file.

        Args:
            path (Path): The file (named in the errors).
            content (Dict[str, JsonValue]): Its content.
            model (type[Model]): The model of its content.

        Returns:
            Model: The validated content.

        Raises:
            CompaniesCatalogError: If the content is invalid.
        """
        try:
            return model.model_validate(content)
        except ValidationError as e:
            self.logger.error("The companies catalogue %s is invalid (%d errors).", path, e.error_count())
            raise CompaniesCatalogError(str(path), f"the content is invalid.\n{e}") from e

    ############################
    # Publicly Exposed Methods #
    ############################

    def concepts(self, path: Path = SETTINGS_PATH) -> FinancialConcepts:
        """Read how the statement lines are mapped.

        Args:
            path (Path): The settings file, whose `concepts` block holds the mapping.

        Returns:
            FinancialConcepts: The XBRL concepts and the Google Finance positions of each line.

        Raises:
            CompaniesCatalogError: If the file cannot be read or is invalid.
        """
        concepts = self._validate(path, self._block(path, self.CONCEPTS_BLOCK), FinancialConcepts)
        self.logger.debug(
            "Financial concepts loaded: %d lines, %d Google positions.",
            len(concepts.concepts),
            len(concepts.google_finance.slots),
        )
        return concepts

    def help(self, path: Path = HELP_PATH) -> FinancialsHelp:
        """Read the tooltips and the menu of the company financials card.

        Args:
            path (Path): The help file, whose `financials` block holds them.

        Returns:
            FinancialsHelp: What each control, family and indicator explains.

        Raises:
            CompaniesCatalogError: If the file cannot be read or is invalid.
        """
        helps = self._validate(path, self._block(path, self.HELP_BLOCK), FinancialsHelp)
        self.logger.debug(
            "Company financials help loaded: %d controls, %d families, %d indicators.",
            len(helps.controls),
            len(helps.families),
            len(helps.indicators),
        )
        return helps
