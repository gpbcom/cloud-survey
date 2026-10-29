from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Dict, Optional

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from conf import PRICE_COVERAGE_DIR
from models.cloud.enums import CloudProvider
from models.cloud.prices.coverage.coverage_catalog import CoverageCatalog


class CoverageCatalogReader:
    """Read the curated price coverage of the providers (`conf/prices/coverage/<provider>.yaml`).

    Attributes:
        directory (Path): The folder of the coverage catalogues, one file per provider.
        logger (Logger): The reader logger.
        cache (Dict[CloudProvider, Optional[CoverageCatalog]]): The catalogues read, by provider.

    Notes:
        A provider without file has no curated coverage.
        A file that cannot be read or is invalid is reported and
        ignored: the price crawl goes on with the automatic matching only.
    """

    def __init__(self, directory: Path = PRICE_COVERAGE_DIR, logger: Optional[Logger] = None) -> None:
        """Initialize the reader.

        Args:
            directory (Path): The folder of the coverage catalogues.
            logger (Optional[Logger]): The reader logger.
        """
        self.directory = directory
        self.logger = logger if logger else getLogger(__name__)
        self.cache: Dict[CloudProvider, Optional[CoverageCatalog]] = {}
        self.logger.debug("Coverage catalogue reader of %s ready.", directory)

    ############################
    # Internal Helpers Methods #
    ############################

    def _load(self, provider: CloudProvider) -> Optional[CoverageCatalog]:
        """Load the coverage catalogue of a provider from its file.

        Args:
            provider (CloudProvider): The provider.

        Returns:
            Optional[CoverageCatalog]: Its catalogue, `None` without file or when the file is invalid.
        """
        path = self.directory / f"{provider.value}.yaml"
        if not path.is_file():
            self.logger.debug("No curated price coverage for %s.", provider.value)
            return None
        try:
            with path.open(encoding="utf-8") as file:
                raw = yaml.safe_load(file) or {}
            catalog = CoverageCatalog.model_validate(raw)
        except OSError as e:
            self.logger.error("The price coverage %s cannot be read: %s", path, e.strerror)
            return None
        except (yaml.YAMLError, ValidationError) as e:
            self.logger.error("The price coverage %s is invalid, it is ignored: %s", path, e)
            return None
        if catalog.provider is not provider:
            self.logger.warning("The price coverage %s states the provider %s: ignored.", path, catalog.provider.value)
            return None
        self.logger.info(
            "Price coverage of %s read: %d linked products, %d statements.",
            provider.value,
            len(catalog.links),
            len(catalog.statements),
        )
        return catalog

    ############################
    # Publicly Exposed Methods #
    ############################

    def read(self, provider: CloudProvider) -> Optional[CoverageCatalog]:
        """Read the coverage catalogue of a provider (once).

        Args:
            provider (CloudProvider): The provider.

        Returns:
            Optional[CoverageCatalog]: Its catalogue, `None` when it has none.
        """
        if provider not in self.cache:
            self.cache[provider] = self._load(provider)
        return self.cache[provider]
