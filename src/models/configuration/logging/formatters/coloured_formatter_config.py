from __future__ import annotations

# Standard Library Imports.
from typing import Dict, Literal, Optional

# Third Party Imports.
from colorlog.escape_codes import escape_codes
from pydantic import Field, JsonValue, field_validator

# First Party Imports.
from models.configuration.logging.enums import LogLevel  # isort: skip
from models.configuration.logging.base.base_formatter_config import BaseFormatterConfig
from models.configuration.logging.exception import InvalidSecondaryColoursNameError, UnknownColourError


class ColouredFormatterConfig(BaseFormatterConfig):
    """`colorlog` colourized log record formatter configuration.

    Attributes:
        factory (Literal["colorlog.ColoredFormatter"]): The formatter factory, `dictConfig` `()` key.
        fmt (str): The log record format string.
        log_colors (Dict[LogLevel, str]): The comma separated `colorlog` colour names, by log level.
        secondary_log_colors (Dict[str, Dict[LogLevel, str]]): Additional colours by log level, each one exposed
            to the format string as a `<name>_log_color` placeholder.
        reset (bool): Whether a colour reset is appended to each record.
        stream (Optional[Literal["ext://sys.stdout", "ext://sys.stderr"]]): Stream checked for colours support.

    Notes:
        The format string selects where colours apply with the `log_color`, `<name>_log_color`, `reset` and
        fixed colour (e.g. `cyan`) placeholders, e.g. `%(log_color)s%(levelname)-8s%(reset)s %(cyan)s%(name)s%(reset)s
        %(message_log_color)s%(message)s`. Colours are disabled when the `NO_COLOR` environment variable is set,
        or when `stream` is not a terminal, unless `FORCE_COLOR` is set.
    """

    factory: Literal["colorlog.ColoredFormatter"] = Field(alias="()", description="The formatter factory.")
    fmt: str = Field(
        validation_alias="format", serialization_alias="fmt", min_length=1, description="The log record format string."
    )
    log_colors: Dict[LogLevel, str] = Field(
        default_factory=lambda: {
            LogLevel.DEBUG: "white",
            LogLevel.INFO: "green",
            LogLevel.WARNING: "yellow",
            LogLevel.ERROR: "red",
            LogLevel.CRITICAL: "bold_red,bg_white",
        },
        description="The comma separated `colorlog` colour names, by log level.",
    )
    secondary_log_colors: Dict[str, Dict[LogLevel, str]] = Field(
        default_factory=dict,
        description="Additional colours by log level, exposed to the format string as `<name>_log_color`.",
    )
    reset: bool = Field(default=True, description="Whether a colour reset is appended to each record.")
    stream: Optional[Literal["ext://sys.stdout", "ext://sys.stderr"]] = Field(
        default=None, description="Stream checked for colours support: no colours when it is not a terminal."
    )

    @field_validator("log_colors", mode="before")
    def validate_log_colors(cls, value: JsonValue) -> JsonValue:
        """Make the raw log colours levels case-insensitive, and ensure every colour is known by `colorlog`.

        Args:
            value (JsonValue): The raw log colours.

        Returns:
            JsonValue: The log colours with upper-cased string levels when given a mapping, the raw value otherwise
                (its type is checked by pydantic afterwards).

        Raises:
            UnknownColourError: If a colour name is unknown.
        """
        normalized = cls.normalize_levels(value)
        if isinstance(normalized, dict):
            cls.check_colours(normalized, scope="")
        return normalized

    @field_validator("secondary_log_colors", mode="before")
    def validate_secondary_log_colors(cls, value: JsonValue) -> JsonValue:
        """Make the raw secondary log colours levels case-insensitive, and ensure they can be used for colouring.

        Args:
            value (JsonValue): The raw secondary log colours.

        Returns:
            JsonValue: The secondary log colours with upper-cased string levels when given a mapping, the raw value
                otherwise (its type is checked by pydantic afterwards).

        Raises:
            InvalidSecondaryColoursNameError: If a secondary colour name is not an identifier.
            UnknownColourError: If a colour name is unknown.
        """
        if not isinstance(value, dict):
            return value
        normalized: Dict[str, JsonValue] = {}
        for name, colours in value.items():
            if not name.isidentifier():
                raise InvalidSecondaryColoursNameError(name)
            colours_by_level = cls.normalize_levels(colours)
            if isinstance(colours_by_level, dict):
                cls.check_colours(colours_by_level, scope=f"`{name}` ")
            normalized[name] = colours_by_level
        return normalized

    @classmethod
    def normalize_levels(cls, value: JsonValue) -> JsonValue:
        """Make the log levels of raw colours case-insensitive.

        Args:
            value (JsonValue): The raw colours, by log level.

        Returns:
            JsonValue: The colours with upper-cased levels when given a mapping, the raw value otherwise.
        """
        if not isinstance(value, dict):
            return value
        return {level.upper(): colours for level, colours in value.items()}

    @classmethod
    def check_colours(cls, colours_by_level: Dict[str, JsonValue], scope: str) -> Dict[str, JsonValue]:
        """Ensure every colour of a raw by-level mapping is known by `colorlog`.

        Non string colours are left to the pydantic validation.

        Args:
            colours_by_level (Dict[str, JsonValue]): The comma separated colour names, by log level.
            scope (str): The mapping name, prefixed to the error message.

        Returns:
            Dict[str, JsonValue]: The checked mapping.

        Raises:
            UnknownColourError: If a colour name is unknown.
        """
        for level, colours in colours_by_level.items():
            if not isinstance(colours, str):
                continue
            if unknown := [colour for colour in colours.split(",") if colour and colour not in escape_codes]:
                raise UnknownColourError(scope, level, unknown)
        return colours_by_level
