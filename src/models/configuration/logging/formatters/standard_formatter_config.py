from __future__ import annotations

# Third Party Imports.
from pydantic import Field

# First Party Imports.
from models.configuration.logging.base.base_formatter_config import BaseFormatterConfig


class StandardFormatterConfig(BaseFormatterConfig):
    """Standard library log record formatter configuration.

    Attributes:
        class_ (str): Dotted path of the formatter class.
        fmt (str): The log record format string.
    """

    class_: str = Field(default="logging.Formatter", alias="class", description="Dotted path of the formatter class.")
    fmt: str = Field(alias="format", min_length=1, description="The log record format string.")
