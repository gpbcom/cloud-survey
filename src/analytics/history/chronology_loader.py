from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Optional

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from analytics.history.exception import ChronologyFileError
from conf import CHRONOLOGY_PATH
from models.history.chronology import Chronology


class ChronologyLoader:
    """Load the leaders of computing and the notable events (`conf/history/chronology.yaml`).

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

    def load(self, path: Path = CHRONOLOGY_PATH) -> Chronology:
        """Read and validate the chronology.

        Args:
            path (Path): The chronology file.

        Returns:
            Chronology: The segments, companies, reigns and events.

        Raises:
            ChronologyFileError: If the file cannot be read, is not valid YAML or holds an invalid chronology.
        """
        try:
            with path.open(encoding="utf-8") as file:
                chronology = Chronology.model_validate(yaml.safe_load(file) or {})
        except OSError as e:
            self.logger.error("The chronology %s cannot be read: %s", path, e.strerror)
            raise ChronologyFileError(path, f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The chronology %s is not valid YAML.", path)
            raise ChronologyFileError(path, f"the file is not valid YAML.\n{e}") from e
        except ValidationError as e:
            self.logger.error("The chronology %s is invalid (%d errors).", path, e.error_count())
            raise ChronologyFileError(path, f"the content is invalid.\n{e}") from e
        empty = [segment.key for segment in chronology.segments if not chronology.reigns_of(segment.key)]
        if empty:
            self.logger.warning("The chronology %s has no leader for: %s.", path, ", ".join(empty))
        self.logger.debug(
            "Chronology loaded: %d segments, %d reigns, %d events.",
            len(chronology.segments),
            len(chronology.reigns),
            len(chronology.events),
        )
        return chronology
