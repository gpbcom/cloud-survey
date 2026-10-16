from __future__ import annotations

# Standard Library Imports.
from pathlib import Path
from typing import Literal, Optional

# Third Party Imports.
from pydantic import Field

# First Party Imports.
from models.configuration.logging.base.base_handler_config import BaseHandlerConfig


class RotatingFileHandlerConfig(BaseHandlerConfig):
    """Size based rotating file handler configuration.

    Attributes:
        class_ (Literal["logging.handlers.RotatingFileHandler"]): Handler class discriminator.
        filename (Path): The log file path.
        mode (Literal["a", "w"]): The file opening mode.
        max_bytes (int): The file size triggering a rotation (0 disables rotation).
        backup_count (int): The number of rotated files kept.
        encoding (Optional[str]): The file encoding.
        delay (bool): Whether the file opening is deferred to the first emitted record.
    """

    class_: Literal["logging.handlers.RotatingFileHandler"] = Field(
        alias="class", description="Handler class discriminator."
    )
    filename: Path = Field(description="The log file path.")
    mode: Literal["a", "w"] = Field(default="a", description="The file opening mode.")
    max_bytes: int = Field(
        default=0, alias="maxBytes", ge=0, description="The file size triggering a rotation (0 disables rotation)."
    )
    backup_count: int = Field(default=0, alias="backupCount", ge=0, description="The number of rotated files kept.")
    encoding: Optional[str] = Field(default="utf-8", description="The file encoding.")
    delay: bool = Field(default=False, description="Whether the file opening is deferred to the first emitted record.")
