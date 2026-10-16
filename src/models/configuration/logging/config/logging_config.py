from __future__ import annotations

# Standard Library Imports.
from typing import Dict, Literal, Self, Union

# Third Party Imports.
from pydantic import Field, JsonValue, model_validator

from models.configuration.logging.base.dict_config_model import DictConfigModel

# First Party Imports.
from models.configuration.logging.exception import UnknownFormatterReferenceError, UnknownHandlerReferenceError
from models.configuration.logging.formatters.formatter_config import FormatterConfig
from models.configuration.logging.handlers.handler_config import HandlerConfig
from models.configuration.logging.loggers.logger_config import LoggerConfig
from models.configuration.logging.loggers.root_logger_config import RootLoggerConfig


class LoggingConfig(DictConfigModel):
    """Application logging configuration, compatible with `logging.config.dictConfig`.

    Attributes:
        version (Literal[1]): The `dictConfig` schema version.
        disable_existing_loggers (bool): Whether loggers created before the configuration are disabled.
        formatters (Dict[str, FormatterConfig]): Formatters by name.
        handlers (Dict[str, HandlerConfig]): Handlers by name.
        loggers (Dict[str, LoggerConfig]): Named loggers configuration.
        root (RootLoggerConfig): Root logger configuration.
    """

    version: Literal[1] = Field(default=1, description="The `dictConfig` schema version.")
    disable_existing_loggers: bool = Field(
        default=False, description="Whether loggers created before the configuration are disabled."
    )
    formatters: Dict[str, FormatterConfig] = Field(default_factory=dict, description="Formatters by name.")
    handlers: Dict[str, HandlerConfig] = Field(default_factory=dict, description="Handlers by name.")
    loggers: Dict[str, LoggerConfig] = Field(default_factory=dict, description="Named loggers configuration.")
    root: RootLoggerConfig = Field(default_factory=RootLoggerConfig, description="Root logger configuration.")

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Ensure every referenced formatter and handler is defined.

        Returns:
            Self: The validated configuration.

        Raises:
            UnknownFormatterReferenceError: If a handler references an unknown formatter.
            UnknownHandlerReferenceError: If a logger references unknown handlers.
        """
        for name, handler in self.handlers.items():
            if handler.formatter is not None and handler.formatter not in self.formatters:
                raise UnknownFormatterReferenceError(name, handler.formatter)

        loggers: Dict[str, Union[LoggerConfig, RootLoggerConfig]] = {**self.loggers, "root": self.root}
        for name, logger in loggers.items():
            if unknown := [handler for handler in logger.handlers if handler not in self.handlers]:
                raise UnknownHandlerReferenceError(name, unknown)
        return self

    def to_dict_config(self) -> Dict[str, JsonValue]:
        """Export the configuration in the `logging.config.dictConfig` format.

        Returns:
            Dict[str, JsonValue]: The configuration ready to be given to `logging.config.dictConfig`.
        """
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)
