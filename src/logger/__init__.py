from __future__ import annotations

# Standard Library Imports.
import logging.config
from logging import Logger, getLogger
from pathlib import Path

# Third Party Imports.
import yaml
from pydantic import ValidationError

# First Party Imports.
from conf import LOGGER_CONFIG_PATH
from logger.exception import LoggingConfigFileError
from models.configuration.logging.config.logging_config import LoggingConfig
from models.configuration.logging.handlers.rotating_file_handler_config import RotatingFileHandlerConfig

logger: Logger = getLogger(__name__)


def load_logging_config(path: Path = LOGGER_CONFIG_PATH) -> LoggingConfig:
    """Load and validate a YAML logging configuration.

    Args:
        path (Path): The YAML configuration file path.

    Returns:
        LoggingConfig: The validated logging configuration.

    Raises:
        LoggingConfigFileError: If the file cannot be read, is not valid YAML, or holds an invalid configuration.
    """
    logger.debug("Loading the logging configuration %s.", path)
    try:
        with path.open(encoding="utf-8") as file:
            config = LoggingConfig.model_validate(yaml.safe_load(file))
    except OSError as e:
        logger.error("The logging configuration %s cannot be read: %s", path, e.strerror)
        raise LoggingConfigFileError(path, f"the file cannot be read ({e.strerror}).") from e
    except yaml.YAMLError as e:
        logger.error("The logging configuration %s is not valid YAML.", path)
        raise LoggingConfigFileError(path, f"the file is not valid YAML.\n{e}") from e
    except ValidationError as e:
        logger.error("The logging configuration %s is invalid (%d errors).", path, e.error_count())
        raise LoggingConfigFileError(path, f"the configuration is invalid.\n{e}") from e
    logger.debug("Logging configuration %s loaded: %d handlers.", path, len(config.handlers))
    return config


def setup_logging(path: Path = LOGGER_CONFIG_PATH) -> LoggingConfig:
    """Configure the application logging from a YAML configuration.

    Args:
        path (Path): The YAML configuration file path.

    Returns:
        LoggingConfig: The applied logging configuration.

    Raises:
        LoggingConfigFileError: If the configuration cannot be loaded.
    """
    config = load_logging_config(path)
    for handler in config.handlers.values():
        if isinstance(handler, RotatingFileHandlerConfig):
            handler.filename.parent.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(config.to_dict_config())
    logger.info("Logging configured from %s (handlers: %s).", path, ", ".join(config.handlers))
    for name, handler in config.handlers.items():
        if isinstance(handler, RotatingFileHandlerConfig):
            logger.debug("The %s handler writes to %s.", name, handler.filename.resolve())
    return config
