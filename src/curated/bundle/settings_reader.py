from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from pathlib import Path
from typing import Dict, Optional

# Third Party Imports.
import yaml
from pydantic import JsonValue

# First Party Imports.
from conf import SETTINGS_PATH
from curated.exception import CuratedBundleError


class SettingsReader:
    """Read a block of the settings (`conf/settings.yaml`): what the curated catalogues are assembled with.

    Attributes:
        path (Path): The settings file.
        logger (Logger): The reader logger.
    """

    def __init__(self, path: Path = SETTINGS_PATH, logger: Optional[Logger] = None) -> None:
        """Initialize the reader.

        Args:
            path (Path): The settings file, `conf/settings.yaml` by default.
            logger (Optional[Logger]): The reader logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.path = path

    ############################
    # Publicly Exposed Methods #
    ############################

    def block(self, name: str) -> Dict[str, JsonValue]:
        """Read one block of the settings.

        Args:
            name (str): The block, e.g. `companies`.

        Returns:
            Dict[str, JsonValue]: Its content.

        Raises:
            CuratedBundleError: If the file cannot be read, is not valid YAML or has no such block.
        """
        try:
            with self.path.open(encoding="utf-8") as file:
                content = yaml.safe_load(file) or {}
        except OSError as e:
            self.logger.error("The settings %s cannot be read: %s", self.path, e.strerror)
            raise CuratedBundleError(str(self.path), f"the file cannot be read ({e.strerror}).") from e
        except yaml.YAMLError as e:
            self.logger.error("The settings %s are not valid YAML.", self.path)
            raise CuratedBundleError(str(self.path), f"the file is not valid YAML.\n{e}") from e
        block = content.get(name) if isinstance(content, dict) else None
        if not isinstance(block, dict):
            self.logger.error("The settings %s have no %s block.", self.path, name)
            raise CuratedBundleError(str(self.path), f"the file has no `{name}` block.")
        self.logger.debug("Settings block %s read.", name)
        return block
