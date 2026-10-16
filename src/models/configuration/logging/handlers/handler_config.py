from __future__ import annotations

# Standard Library Imports.
from typing import Annotated, Union

# Third Party Imports.
from pydantic import Field

# First Party Imports.
from models.configuration.logging.handlers.rotating_file_handler_config import RotatingFileHandlerConfig
from models.configuration.logging.handlers.stream_handler_config import StreamHandlerConfig

# Every supported handler configuration, selected from its `class` key.
HandlerConfig = Annotated[Union[StreamHandlerConfig, RotatingFileHandlerConfig], Field(discriminator="class_")]
