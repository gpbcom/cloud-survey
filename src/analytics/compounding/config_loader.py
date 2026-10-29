from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Optional

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from analytics.compounding.exception import CompoundingFileError, UnknownCompoundingSlugError
from conf import COMPOUNDING_PATH
from models.compounding.config.compounding_config import CompoundingConfig
from models.taxonomy.nodes.taxonomy import Taxonomy


class CompoundingConfigLoader:
    """Load the scope and the curated inputs of the service-compounding analysis.

    Attributes:
        logger (Logger): The loader logger.

    Notes:
        The file is `conf/analysis/compounding.yaml`. Its domains must be taxonomy domains, its foundation sets
        taxonomy categories, when a taxonomy is given to check them against.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _check(self, config: CompoundingConfig, taxonomy: Taxonomy) -> None:
        """Check the slugs of the configuration against the taxonomy.

        Args:
            config (CompoundingConfig): The configuration.
            taxonomy (Taxonomy): The taxonomy.

        Raises:
            UnknownCompoundingSlugError: If a domain or a category is not in the taxonomy.
        """
        for domain in config.domains:
            if not taxonomy.is_domain(domain):
                self.logger.error("The compounding domain %s is not a taxonomy domain.", domain)
                raise UnknownCompoundingSlugError("domain", domain)
        for entry in config.foundations:
            for slug in [entry.category, *entry.foundations()]:
                if not taxonomy.is_category(slug):
                    self.logger.error("The compounding category %s is not a taxonomy category.", slug)
                    raise UnknownCompoundingSlugError("category", slug)

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self, path: Path = COMPOUNDING_PATH, taxonomy: Optional[Taxonomy] = None) -> CompoundingConfig:
        """Read and validate the configuration.

        Args:
            path (Path): The configuration file.
            taxonomy (Optional[Taxonomy]): The taxonomy to check the slugs against, none to skip the check.

        Returns:
            CompoundingConfig: The configuration.

        Raises:
            CompoundingFileError: If the file cannot be read, is not valid YAML or is invalid.
            UnknownCompoundingSlugError: If a domain or a category is not in the taxonomy.
        """
        try:
            with path.open(encoding="utf-8") as file:
                config = CompoundingConfig.model_validate(yaml.safe_load(file) or {})
        except OSError as e:
            self.logger.error("The compounding configuration %s cannot be read: %s", path, e.strerror)
            raise CompoundingFileError(str(path), f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The compounding configuration %s is not valid YAML.", path)
            raise CompoundingFileError(str(path), f"the file is not valid YAML.\n{e}") from e
        except ValidationError as e:
            self.logger.error("The compounding configuration %s is invalid (%d errors).", path, e.error_count())
            raise CompoundingFileError(str(path), f"the content is invalid.\n{e}") from e
        if taxonomy is not None:
            self._check(config, taxonomy)
        if not config.market:
            self.logger.warning("The compounding configuration holds no curated market size.")
        self.logger.info(
            "Compounding configuration loaded: %d providers, %d domains, %d foundation sets.",
            len(config.providers),
            len(config.domains),
            len(config.foundations),
        )
        return config
