from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Final, Optional

# Third Party Imports.
from pydantic import ValidationError

# First Party Imports.
from catalogue.atomic_json_file import AtomicJsonFile
from catalogue.exception import CatalogueFileError, CatalogueWriteError
from models.stats.market_statistics import MarketStatistics

DEFAULT_STATISTICS_DIR: Final[Path] = Path("output") / "stats"


class StatisticsStore:
    """Store of the crawled market statistics: one `<source>.json` file per market research firm.

    Attributes:
        output_dir (Path): The folder holding the statistics files, created on the first save.
        logger (Logger): The store logger.
    """

    def __init__(self, output_dir: Path = DEFAULT_STATISTICS_DIR, logger: Optional[Logger] = None) -> None:
        """Initialize the store.

        Args:
            output_dir (Path): The folder holding the statistics files, created on the first save.
            logger (Optional[Logger]): The store logger.
        """
        self.output_dir = output_dir
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def path_for(self, name: str) -> Path:
        """Get the statistics file path of a source.

        Args:
            name (str): The source crawler name, e.g. `synergy`.

        Returns:
            Path: The statistics file path, e.g. `output/stats/synergy.json`.
        """
        return self.output_dir / f"{name}.json"

    def save(self, name: str, statistics: MarketStatistics) -> Path:
        """Write the statistics file of a source, atomically.

        Args:
            name (str): The source crawler name, e.g. `synergy`.
            statistics (MarketStatistics): The statistics to write.

        Returns:
            Path: The written statistics file path.

        Raises:
            CatalogueWriteError: If the folder or the file cannot be written.
        """
        path = self.path_for(name)
        self.logger.debug("Writing the %s statistics to %s.", statistics.source, path)
        try:
            AtomicJsonFile(path).write(statistics.model_dump_json(indent=2))
        except OSError as e:
            self.logger.error("The %s statistics cannot be written to %s: %s", statistics.source, path, e)
            raise CatalogueWriteError(path, e.strerror or str(e)) from e
        self.logger.info("%d %s market reports written to %s.", statistics.size, statistics.source, path)
        return path

    def load(self, name: str) -> Optional[MarketStatistics]:
        """Read the statistics file of a source.

        Args:
            name (str): The source crawler name, e.g. `synergy`.

        Returns:
            Optional[MarketStatistics]: The statistics, `None` when the source was never crawled (no file).

        Raises:
            CatalogueFileError: If the file cannot be read or does not hold valid statistics.
        """
        path = self.path_for(name)
        if not path.exists():
            self.logger.debug("No %s statistics at %s: never crawled.", name, path)
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as e:
            self.logger.error("The %s statistics %s cannot be read: %s", name, path, e)
            raise CatalogueFileError(path, f"the file cannot be read ({e.strerror})") from e
        try:
            statistics = MarketStatistics.model_validate_json(raw)
        except ValidationError as e:
            is_json = all(error["type"] != "json_invalid" for error in e.errors())
            reason = f"invalid statistics ({e.error_count()} errors)" if is_json else "the file is not valid JSON"
            self.logger.error("The %s statistics %s are unusable: %s.", name, path, reason)
            raise CatalogueFileError(path, reason) from e
        self.logger.info("%d %s market reports loaded from %s.", statistics.size, statistics.source, path)
        return statistics
