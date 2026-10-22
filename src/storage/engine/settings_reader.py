from __future__ import annotations

# Standard Library Imports.
import os
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple, Union

# Third Party Imports.
from pydantic import ValidationError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# First Party Imports.
from models.configuration.storage.storage_settings import StorageSettings


class StorageSettingsReader:
    """Read the storage settings from the environment, the defaults filling the missing or invalid variables.

    Attributes:
        URL_VARIABLE (ClassVar[str]): The environment variable holding the database URL.
        NUMBER_VARIABLES (ClassVar[Dict[str, str]]): The environment variables holding the numeric settings, by
            setting.
        ECHO_VARIABLE (ClassVar[str]): The environment variable turning the SQL logging on (`1`, `true`, `yes`).
        TRUE_VALUES (ClassVar[Tuple[str, ...]]): The values turning a flag on.
        logger (Logger): The reader logger.
    """

    URL_VARIABLE: ClassVar[str] = "CRAWLER_DATABASE_URL"
    NUMBER_VARIABLES: ClassVar[Dict[str, str]] = {
        "pool_size": "CRAWLER_DATABASE_POOL_SIZE",
        "max_overflow": "CRAWLER_DATABASE_MAX_OVERFLOW",
        "batch_size": "CRAWLER_DATABASE_BATCH_SIZE",
    }
    ECHO_VARIABLE: ClassVar[str] = "CRAWLER_DATABASE_ECHO"
    TRUE_VALUES: ClassVar[Tuple[str, ...]] = ("1", "true", "yes", "on")

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the reader.

        Args:
            logger (Optional[Logger]): The reader logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Storage settings reader ready (%s).", self.URL_VARIABLE)

    ############################
    # Internal Helpers Methods #
    ############################

    def _numbers(self) -> Dict[str, int]:
        """Read the numeric settings set in the environment.

        Returns:
            Dict[str, int]: The valid positive numbers, by setting (an invalid one is logged and left to its default).
        """
        numbers: Dict[str, int] = {}
        for setting, variable in self.NUMBER_VARIABLES.items():
            raw = os.getenv(variable, "").strip()
            if not raw:
                continue
            if raw.isdigit():
                numbers[setting] = int(raw)
            else:
                self.logger.warning("%s=%r is not a number: the default %s is used.", variable, raw, setting)
        return numbers

    ############################
    # Publicly Exposed Methods #
    ############################

    def safe_url(self, url: str) -> str:
        """Get a database URL which can be logged: without its password.

        Args:
            url (str): The database URL.

        Returns:
            str: The URL with its password masked, the URL unchanged when it cannot be parsed.
        """
        try:
            return make_url(url).render_as_string(hide_password=True)
        except ArgumentError, ValueError:
            return url

    def read(self) -> StorageSettings:
        """Read the storage settings from the environment.

        Returns:
            StorageSettings: The settings, the defaults replacing the missing or invalid values (logged).
        """
        values: Dict[str, Union[str, int, bool]] = {**self._numbers()}
        url = os.getenv(self.URL_VARIABLE, "").strip()
        if url:
            values["url"] = url
        values["echo"] = os.getenv(self.ECHO_VARIABLE, "").strip().casefold() in self.TRUE_VALUES
        try:
            settings = StorageSettings.model_validate(values)
        except ValidationError as e:
            invalid = sorted({str(error["loc"][0]) for error in e.errors() if error["loc"]})
            self.logger.warning("Invalid storage settings (%s): their defaults are used.", ", ".join(invalid))
            settings = StorageSettings.model_validate(
                {key: value for key, value in values.items() if key not in invalid}
            )
        self.logger.debug(
            "Storage settings: %s, pool of %d (+%d), batches of %d.",
            self.safe_url(settings.url),
            settings.pool_size,
            settings.max_overflow,
            settings.batch_size,
        )
        return settings
