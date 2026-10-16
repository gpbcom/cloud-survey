from __future__ import annotations

from typing import List

# Third Party Imports.
from pydantic import Field

# First Party Imports.
from models.configuration.logging.base.levelled_model import LevelledModel
from models.configuration.logging.enums import LogLevel


class RootLoggerConfig(LevelledModel):
    """Root logger configuration.

    Attributes:
        level (LogLevel): The minimum severity handled.
        handlers (List[str]): Names of the handlers attached to the root logger.
    """

    level: LogLevel = Field(default=LogLevel.WARNING, description="The minimum severity handled.")
    handlers: List[str] = Field(default_factory=list, description="Names of the handlers attached to the root logger.")
