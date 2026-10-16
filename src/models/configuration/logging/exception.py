from __future__ import annotations

# Standard Library Imports.
from typing import List


class LoggingConfigurationError(ValueError):
    """Base class for every logging configuration validation error.

    It is a `ValueError`, so pydantic reports it as a `ValidationError` when raised by a validator.

    Attributes:
        message (str): Human-readable description of the error.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message (str): Human-readable description of the error.
        """
        self.message = message
        super().__init__(message)


class UnknownFormatterReferenceError(LoggingConfigurationError):
    """Raised when a handler references a formatter which is not configured.

    Attributes:
        handler (str): The handler name.
        formatter (str): The unknown formatter name.
    """

    def __init__(self, handler: str, formatter: str) -> None:
        """Initialize the error.

        Args:
            handler (str): The handler name.
            formatter (str): The unknown formatter name.
        """
        self.handler = handler
        self.formatter = formatter
        super().__init__(f"Handler '{handler}' references an unknown formatter: '{formatter}'.")


class UnknownHandlerReferenceError(LoggingConfigurationError):
    """Raised when a logger references handlers which are not configured.

    Attributes:
        logger (str): The logger name.
        handlers (List[str]): The unknown handler names.
    """

    def __init__(self, logger: str, handlers: List[str]) -> None:
        """Initialize the error.

        Args:
            logger (str): The logger name.
            handlers (List[str]): The unknown handler names.
        """
        self.logger = logger
        self.handlers = handlers
        super().__init__(f"Logger '{logger}' references unknown handler(s): {', '.join(handlers)}.")


class InvalidSecondaryColoursNameError(LoggingConfigurationError):
    """Raised when a secondary log colours name cannot be used as a format placeholder.

    Attributes:
        name (str): The rejected secondary log colours name.
    """

    def __init__(self, name: str) -> None:
        """Initialize the error.

        Args:
            name (str): The rejected secondary log colours name.
        """
        self.name = name
        super().__init__(f"Secondary log colours name '{name}' must be a valid identifier.")


class UnknownColourError(LoggingConfigurationError):
    """Raised when a log level colour is unknown by `colorlog`.

    Attributes:
        scope (str): The colours mapping name, prefixed to the error message (empty for `log_colors`).
        level (str): The log level the colours apply to.
        colours (List[str]): The unknown colour names.
    """

    def __init__(self, scope: str, level: str, colours: List[str]) -> None:
        """Initialize the error.

        Args:
            scope (str): The colours mapping name, prefixed to the error message (empty for `log_colors`).
            level (str): The log level the colours apply to.
            colours (List[str]): The unknown colour names.
        """
        self.scope = scope
        self.level = level
        self.colours = colours
        super().__init__(f"Unknown {scope}colour(s) for level {level}: {', '.join(colours)}.")
