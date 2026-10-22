from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Optional

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from conf import METRIC_COLLECTORS_PATH
from crawler.exception import CollectorCatalogError
from models.drivers.collectors.collector_catalog import CollectorCatalog


class CollectorCatalogLoader:
    """Load where the metrics crawlers find each provider (`conf/metrics/collectors.yaml`).

    Attributes:
        logger (Logger): The loader logger.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self, path: Path = METRIC_COLLECTORS_PATH) -> CollectorCatalog:
        """Read and validate the catalogue.

        Args:
            path (Path): The catalogue file.

        Returns:
            CollectorCatalog: Where each provider is found.

        Raises:
            CollectorCatalogError: If the file cannot be read, is not valid YAML or is invalid.
        """
        try:
            with path.open(encoding="utf-8") as file:
                catalog = CollectorCatalog.model_validate(yaml.safe_load(file) or {})
        except OSError as e:
            self.logger.error("The metric sources catalogue %s cannot be read: %s", path, e.strerror)
            raise CollectorCatalogError(str(path), f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The metric sources catalogue %s is not valid YAML.", path)
            raise CollectorCatalogError(str(path), f"the file is not valid YAML.\n{e}") from e
        except ValidationError as e:
            self.logger.error("The metric sources catalogue %s is invalid (%d errors).", path, e.error_count())
            raise CollectorCatalogError(str(path), f"the content is invalid.\n{e}") from e
        self.logger.debug("Metric sources catalogue loaded: %d providers.", len(catalog.entries))
        return catalog
