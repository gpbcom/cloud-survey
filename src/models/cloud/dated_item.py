from __future__ import annotations

# Standard Library Imports.
from datetime import UTC, date, datetime
from typing import ClassVar, Dict, List, Optional, Tuple, Union

# Third Party Imports.
from pydantic import BaseModel, Field, JsonValue, SerializerFunctionWrapHandler, field_validator, model_serializer

# First Party Imports.
from models.cloud.enums import DateSource
from models.cloud.exception import InvalidDateError

MILLISECONDS_THRESHOLD = 100_000_000_000
DATE_FIELDS = ("added_at", "added_from", "updated_at", "updated_from", "deleted_at")


class DatedItem(BaseModel):
    """Base class of the crawled items (products and software) which keep the dates of their history.

    Attributes:
        CONTENT_FIELDS (ClassVar[Tuple[str, ...]]): The fields whose change makes an update.
        added_at (Optional[datetime]): When the item was added, timezone-aware, `None` when unknown.
        added_from (Optional[DateSource]): Where `added_at` comes from.
        updated_at (Optional[datetime]): When the item was last updated, timezone-aware, `None` when unknown.
        updated_from (Optional[DateSource]): Where `updated_at` comes from.
        deleted_at (Optional[datetime]): When the item disappeared from the website, `None` while it is listed.

    Notes:
        A crawler sets `added_at` and `updated_at` when the website publishes them. The other dates are observed by
        comparing a crawl with the previous one, see `catalogue.item_history.ItemHistory`.
    """

    CONTENT_FIELDS: ClassVar[Tuple[str, ...]] = ()

    added_at: Optional[datetime] = Field(default=None, description="When the item was added, timezone-aware.")
    added_from: Optional[DateSource] = Field(default=None, description="Where the added date comes from.")
    updated_at: Optional[datetime] = Field(default=None, description="When the item was last updated, timezone-aware.")
    updated_from: Optional[DateSource] = Field(default=None, description="Where the updated date comes from.")
    deleted_at: Optional[datetime] = Field(default=None, description="When the item disappeared from the website.")

    @field_validator("added_at", "updated_at", "deleted_at", mode="before")
    def validate_dates(cls, value: Union[JsonValue, date]) -> Union[JsonValue, date]:
        """Validate the raw dates: ISO 8601 texts, Unix timestamps (in seconds or milliseconds) or dates.

        Args:
            value (Union[JsonValue, date]): The raw date.

        Returns:
            Union[JsonValue, date]: The date in UTC (a raw date without timezone is taken as UTC), `None` when missing,
                blank or a non-positive timestamp.

        Raises:
            InvalidDateError: If the text is neither an ISO 8601 date nor a timestamp.
        """
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if text.isdigit():
                value = int(text)
            else:
                try:
                    parsed = datetime.fromisoformat(text)
                except ValueError as e:
                    raise InvalidDateError(text) from e
                value = parsed
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value <= 0:
                return None
            seconds = value / 1000 if value >= MILLISECONDS_THRESHOLD else value
            return datetime.fromtimestamp(seconds, UTC)
        if isinstance(value, datetime):
            return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=UTC)
        return value

    @model_serializer(mode="wrap")
    def serialize_dates_last(self, handler: SerializerFunctionWrapHandler) -> Dict[str, JsonValue]:
        """Serialize the item with its dates after its content, for readable files.

        Args:
            handler (SerializerFunctionWrapHandler): The default serializer.

        Returns:
            Dict[str, JsonValue]: The serialized fields, the dates last.
        """
        data: Dict[str, JsonValue] = handler(self)
        dates = {key: data.pop(key) for key in DATE_FIELDS if key in data}
        return {**data, **dates}

    def item_dump(self) -> Dict[str, JsonValue]:
        """Serialize the item as a crawler streams it: the dates it has, not the empty ones.

        Returns:
            Dict[str, JsonValue]: The JSON fields, without the missing dates.
        """
        data: Dict[str, JsonValue] = self.model_dump(mode="json")
        return {key: value for key, value in data.items() if key not in DATE_FIELDS or value is not None}

    @property
    def is_deleted(self) -> bool:
        """Tell whether the item disappeared from the website.

        Returns:
            bool: Whether it has a deletion date, not serialized.
        """
        return self.deleted_at is not None

    def fingerprint(self) -> str:
        """Get the content of the item which, when it changes, makes an update.

        Returns:
            str: The JSON of the content fields, without the dates and the derived fields.
        """
        return self.model_dump_json(include=set(self.CONTENT_FIELDS))

    def match_keys(self) -> List[str]:
        """Get the keys recognizing the item in another crawl, the most reliable first.

        Returns:
            List[str]: The keys, none for the base class.
        """
        return []
