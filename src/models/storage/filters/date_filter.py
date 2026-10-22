from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import List, Optional, Union

# Third Party Imports.
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.cloud.enums import DateSource
from models.storage.filters.exception import InvalidDateRangeError


class DateFilter(BaseModel):
    """A filter on a history date of the stored items (added, updated or deleted).

    Attributes:
        after (Optional[AwareDatetime]): The items whose date is at or after this instant only.
        before (Optional[AwareDatetime]): The items whose date is before this instant only.
        sources (List[DateSource]): The items whose date comes from one of these sources only (ignored for the
            deletion date, always observed by a crawl).
        known (Optional[bool]): The items whose date is known (`True`) or unknown (`False`) only, `None` for both.
    """

    model_config = ConfigDict(frozen=True)

    after: Optional[AwareDatetime] = Field(default=None, description="The items dated at or after this instant.")
    before: Optional[AwareDatetime] = Field(default=None, description="The items dated before this instant.")
    sources: List[DateSource] = Field(default_factory=list, description="The items dated by these sources.")
    known: Optional[bool] = Field(default=None, description="The items whose date is known, or unknown.")

    @field_validator("before", mode="before")
    def validate_before(cls, value: Union[JsonValue, datetime], info: ValidationInfo) -> Union[JsonValue, datetime]:
        """Validate the end of the range: it cannot come before its start.

        Args:
            value (Union[JsonValue, datetime]): The raw end of the range.
            info (ValidationInfo): The fields validated before, with the start of the range.

        Returns:
            Union[JsonValue, datetime]: The unchanged end (its type is checked by pydantic afterwards).

        Raises:
            InvalidDateRangeError: If the range ends before it starts.
        """
        after = info.data.get("after")
        if isinstance(value, datetime) and isinstance(after, datetime) and value < after:
            raise InvalidDateRangeError(after, value)
        return value

    @property
    def is_active(self) -> bool:
        """Tell whether the filter filters anything.

        Returns:
            bool: Whether a bound, a source or the knowledge of the date is set.
        """
        return self.after is not None or self.before is not None or bool(self.sources) or self.known is not None
