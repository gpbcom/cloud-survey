from __future__ import annotations

from typing import List

# Third Party Imports.
from pydantic import Field

# First Party Imports.
from models.configuration.logging.base.levelled_model import LevelledModel


class LoggerConfig(LevelledModel):
    """Named logger configuration.

    Attributes:
        handlers (List[str]): Names of the handlers attached to this logger.
        propagate (bool): Whether records are passed to the parent logger handlers.
    """

    handlers: List[str] = Field(default_factory=list, description="Names of the handlers attached to this logger.")
    propagate: bool = Field(default=True, description="Whether records are passed to the parent logger handlers.")
