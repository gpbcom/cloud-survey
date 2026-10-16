from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict


class DictConfigModel(BaseModel):
    """Base model for `logging.config.dictConfig` sections.

    Notes:
        Fields use snake_case names in Python and the
        `dictConfig` key names (e.g. `class`, `maxBytes`) as aliases.
        Unknown keys are rejected.
    """

    model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True)
