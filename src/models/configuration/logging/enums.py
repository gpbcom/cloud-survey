from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class LogLevel(StrEnum):
    """Enums representing the standard logging levels.

    Attributes:
        NOTSET (str): Delegate the level to the parent logger.
        DEBUG (str): Detailed diagnostic information.
        INFO (str): Confirmation that things are working as expected.
        WARNING (str): Something unexpected happened, the program still works.
        ERROR (str): A function could not be performed.
        CRITICAL (str): The program itself may be unable to continue.
    """

    NOTSET = "NOTSET"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@unique
class FormatterKind(StrEnum):
    """Enums representing the supported kinds of log record formatter.

    Attributes:
        STANDARD (str): Standard library formatter, configured with the `class` key.
        COLOURED (str): `colorlog` colourized formatter, configured with the `()` factory key.
    """

    STANDARD = "standard"
    COLOURED = "coloured"
