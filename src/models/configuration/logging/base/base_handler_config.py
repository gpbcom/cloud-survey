from __future__ import annotations

from typing import List, Optional

# Third Party Imports.
from pydantic import Field

# First Party Imports.
from models.configuration.logging.base.levelled_model import LevelledModel


class BaseHandlerConfig(LevelledModel):
    """Configuration shared by every log handler.

    Attributes:
        formatter (Optional[str]): Name of the formatter used by this handler.
        filters (List[str]): Names of the filters applied by this handler.
    """

    formatter: Optional[str] = Field(default=None, description="Name of the formatter used by this handler.")
    filters: List[str] = Field(default_factory=list, description="Names of the filters applied by this handler.")
