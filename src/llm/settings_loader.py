from __future__ import annotations

# Standard Library Imports.
import os
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Optional

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from conf import LLM_CONFIG_PATH
from llm.exception import LLMConfigurationFileError
from models.configuration.llm.llm_settings import LLMSettings


class LLMSettingsLoader:
    """Read the language model settings (`conf/llm.yaml`, or the file named by `CRAWLER_LLM_CONFIG`).

    Attributes:
        PATH_VARIABLE (ClassVar[str]): The environment variable naming another settings file.
        logger (Logger): The loader logger.

    Notes:
        A missing file means no model: the settings are then empty, and nothing is sent to a model.
    """

    PATH_VARIABLE: ClassVar[str] = "CRAWLER_LLM_CONFIG"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def path(self) -> Path:
        """Get the settings file.

        Returns:
            Path: The file named by `CRAWLER_LLM_CONFIG`, else `conf/llm.yaml`.
        """
        named = os.getenv(self.PATH_VARIABLE, "").strip()
        return Path(named) if named else LLM_CONFIG_PATH

    def load(self, path: Optional[Path] = None) -> LLMSettings:
        """Read the settings.

        Args:
            path (Optional[Path]): The settings file, `path()` by default.

        Returns:
            LLMSettings: The settings, empty (no model) when the file does not exist.

        Raises:
            LLMConfigurationFileError: If the file cannot be read, is not YAML or holds invalid settings.
        """
        source = path if path is not None else self.path()
        if not source.is_file():
            self.logger.warning("No language model settings at %s: no model is used.", source)
            return LLMSettings()
        try:
            raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
        except OSError as e:
            self.logger.error("The language model settings %s cannot be read: %s", source, e)
            raise LLMConfigurationFileError(source, "the file cannot be read") from e
        except yaml.YAMLError as e:
            self.logger.error("The language model settings %s are not valid YAML: %s", source, e)
            raise LLMConfigurationFileError(source, "the file is not valid YAML") from e
        try:
            settings = LLMSettings.model_validate(raw)
        except (ValidationError, ValueError) as e:
            self.logger.error("The language model settings %s are invalid: %s", source, e)
            raise LLMConfigurationFileError(source, f"the settings are invalid ({e})") from e
        self.logger.info("Language model settings read from %s.", source)
        return settings
