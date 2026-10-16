from __future__ import annotations

# Standard Library Imports.
from typing import Literal, Optional

# Third Party Imports.
from pydantic import Field

# First Party Imports.
from models.configuration.logging.base.dict_config_model import DictConfigModel


class BaseFormatterConfig(DictConfigModel):
    """Configuration shared by every log record formatter.

    Attributes:
        datefmt (Optional[str]): The `strftime` format used for `asctime`.
        style (Literal["%", "{", "$"]): The format string style.
    """

    datefmt: Optional[str] = Field(default=None, description="The `strftime` format used for `asctime`.")
    style: Literal["%", "{", "$"] = Field(default="%", description="The format string style.")
