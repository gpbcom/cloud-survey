from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Optional

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from analytics.drivers.exception import MetricCatalogFileError
from conf import METRICS_CATALOG_PATH
from models.drivers.metrics.metric_catalog import MetricCatalog


class MetricCatalogLoader:
    """Load the catalogue of the criteria and the targets of the driver analysis (`conf/metrics/metrics.yaml`).

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

    def load(self, path: Path = METRICS_CATALOG_PATH) -> MetricCatalog:
        """Read and validate the catalogue.

        Args:
            path (Path): The catalogue file.

        Returns:
            MetricCatalog: Its definitions, in display order.

        Raises:
            MetricCatalogFileError: If the file cannot be read, is not valid YAML or holds invalid definitions.
        """
        self.logger.debug("Loading the metric catalogue %s.", path)
        try:
            with path.open(encoding="utf-8") as file:
                catalog = MetricCatalog.model_validate(yaml.safe_load(file) or {})
        except OSError as e:
            self.logger.error("The metric catalogue %s cannot be read: %s", path, e.strerror)
            raise MetricCatalogFileError(path, f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The metric catalogue %s is not valid YAML.", path)
            raise MetricCatalogFileError(path, f"the file is not valid YAML.\n{e}") from e
        except ValidationError as e:
            self.logger.error("The metric catalogue %s is invalid (%d errors).", path, e.error_count())
            raise MetricCatalogFileError(path, f"the content is invalid.\n{e}") from e
        if not catalog.definitions:
            self.logger.warning("The metric catalogue %s defines no metric.", path)
        self.logger.info(
            "Metric catalogue loaded: %d metrics, %d targets.", len(catalog.definitions), len(catalog.targets())
        )
        return catalog
