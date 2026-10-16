from __future__ import annotations

# Standard Library Imports.
from typing import Literal

# Third Party Imports.
from pydantic import Field

# First Party Imports.
from models.configuration.logging.base.base_handler_config import BaseHandlerConfig


class StreamHandlerConfig(BaseHandlerConfig):
    """Console handler configuration.

    Attributes:
        class_ (Literal["logging.StreamHandler"]): Handler class discriminator.
        stream (Literal["ext://sys.stdout", "ext://sys.stderr"]): The output stream.
    """

    class_: Literal["logging.StreamHandler"] = Field(alias="class", description="Handler class discriminator.")
    stream: Literal["ext://sys.stdout", "ext://sys.stderr"] = Field(
        default="ext://sys.stderr", description="The output stream."
    )
