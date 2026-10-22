from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import List, Optional

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from conf import MANUAL_METRICS_PATH
from models.drivers.enums import MetricSource
from models.drivers.metrics.manual_metric_set import ManualMetricSet
from models.drivers.metrics.provider_metric_value import ProviderMetricValue
from storage.exception import StorageImportError


class ManualMetricLoader:
    """Read the measures typed in from annual reports and analyst publications (`conf/metrics/manual-metrics.yaml`).

    Attributes:
        path (Path): The file.
        logger (Logger): The loader logger.
    """

    def __init__(self, path: Path = MANUAL_METRICS_PATH, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            path (Path): The file.
            logger (Optional[Logger]): The loader logger.
        """
        self.path = path
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def load(self) -> List[ProviderMetricValue]:
        """Read the measures.

        Returns:
            List[ProviderMetricValue]: The measures, their source set to manual (none when the file is missing).

        Raises:
            StorageImportError: If the file cannot be read or holds invalid measures.
        """
        if not self.path.is_file():
            self.logger.info("No manual provider metrics at %s.", self.path)
            return []
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
            values = ManualMetricSet.model_validate(raw).values
        except (OSError, yaml.YAMLError, ValidationError) as e:
            self.logger.error("The manual provider metrics %s cannot be read: %s", self.path, e)
            raise StorageImportError(str(self.path), f"invalid manual provider metrics ({e})") from e
        manual = [value.model_copy(update={"source": MetricSource.MANUAL}) for value in values]
        self.logger.info("%d manual provider metrics read from %s.", len(manual), self.path)
        return manual
