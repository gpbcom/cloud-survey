from __future__ import annotations

# Standard Library Imports.
from datetime import UTC, date, datetime
from hashlib import blake2b
from typing import ClassVar, Dict, List, Optional, Tuple, Union

# Third Party Imports.
from pydantic import BaseModel, Field, JsonValue, SerializerFunctionWrapHandler, field_validator, model_serializer

# First Party Imports.
from models.cloud.enums import DateCaveat, DateSource
from models.cloud.exception import InvalidDateError
from models.cloud.item_state import ItemState

MILLISECONDS_THRESHOLD = 100_000_000_000
FINGERPRINT_SIZE = 16
DATE_FIELDS = (
    "added_at",
    "added_from",
    "added_caveat",
    "updated_at",
    "updated_from",
    "updated_caveat",
    "deleted_at",
)


class DatedItem(BaseModel):
    """Base class of the crawled items (products and software) which keep the dates of their history.

    Attributes:
        CONTENT_FIELDS (ClassVar[Tuple[str, ...]]): The fields whose change makes an update.
        STREAMED_IF_SET (ClassVar[Tuple[str, ...]]): The optional fields a crawler streams only when they are set.
        STREAMED_IF_FILLED (ClassVar[Tuple[str, ...]]): The list fields a crawler streams only when they are not empty.
        added_at (Optional[datetime]): When the item was added, timezone-aware, `None` when unknown.
        added_from (Optional[DateSource]): Where `added_at` comes from.
        added_caveat (Optional[DateCaveat]): Why the website's `added_at` may not be the launch, if it may not.
        updated_at (Optional[datetime]): When the item was last updated, timezone-aware, `None` when unknown.
        updated_from (Optional[DateSource]): Where `updated_at` comes from.
        updated_caveat (Optional[DateCaveat]): Why the website's `updated_at` may not be a change of the item, if it
            may not.
        deleted_at (Optional[datetime]): When the item disappeared from the website, `None` while it is listed.

    Notes:
        A crawler sets `added_at` and `updated_at` when the website publishes them. The other dates are observed by
        comparing a crawl with the previous one, see `catalogue.history.item_history.ItemHistory`.
    """

    CONTENT_FIELDS: ClassVar[Tuple[str, ...]] = ()
    STREAMED_IF_SET: ClassVar[Tuple[str, ...]] = ()
    STREAMED_IF_FILLED: ClassVar[Tuple[str, ...]] = ()

    added_at: Optional[datetime] = Field(default=None, description="When the item was added, timezone-aware.")
    added_from: Optional[DateSource] = Field(default=None, description="Where the added date comes from.")
    added_caveat: Optional[DateCaveat] = Field(default=None, description="Why the added date may be inaccurate.")
    updated_at: Optional[datetime] = Field(default=None, description="When the item was last updated, timezone-aware.")
    updated_from: Optional[DateSource] = Field(default=None, description="Where the updated date comes from.")
    updated_caveat: Optional[DateCaveat] = Field(default=None, description="Why the updated date may be inaccurate.")
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
        match value:
            case bool():
                return value
            case int() | float() if value <= 0:
                return None
            case int() | float():
                seconds = value / 1000 if value >= MILLISECONDS_THRESHOLD else value
                return datetime.fromtimestamp(seconds, UTC)
            case datetime():
                return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
            case date():
                return datetime(value.year, value.month, value.day, tzinfo=UTC)
            case _:
                return value

    @model_serializer(mode="wrap")
    def serialize_dates_last(self, handler: SerializerFunctionWrapHandler) -> Dict[str, Union[JsonValue, datetime]]:
        """Serialize the item with its dates after its content, for readable files.

        Args:
            handler (SerializerFunctionWrapHandler): The default serializer.

        Returns:
            Dict[str, Union[JsonValue, datetime]]: The serialized fields, the dates last: `datetime` values in Python
                mode, ISO texts in JSON mode.
        """
        data: Dict[str, Union[JsonValue, datetime]] = handler(self)
        dates = {key: data.pop(key) for key in DATE_FIELDS if key in data}
        return {**data, **dates}

    def item_dump(self) -> Dict[str, JsonValue]:
        """Serialize the item as a crawler streams it: the dates (and optional fields) it has, not the empty ones.

        Returns:
            Dict[str, JsonValue]: The JSON fields, without the missing dates and `STREAMED_IF_SET` fields, nor the
                empty `STREAMED_IF_FILLED` lists.
        """
        data: Dict[str, JsonValue] = self.model_dump(mode="json")
        optional = {*DATE_FIELDS, *self.STREAMED_IF_SET}
        return {
            key: value
            for key, value in data.items()
            if (key not in optional or value is not None) and (key not in self.STREAMED_IF_FILLED or value)
        }

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

    def fingerprint_hash(self) -> bytes:
        """Get a short hash of the content of the item, to compare it with a stored version.

        Returns:
            bytes: The 16 bytes BLAKE2b digest of `fingerprint()`.
        """
        return blake2b(self.fingerprint().encode("utf-8"), digest_size=FINGERPRINT_SIZE).digest()

    def state(self) -> ItemState:
        """Get what the history of the next crawl needs from this item: its dates and its content fingerprint.

        Returns:
            ItemState: The dates and the content hash of the item.
        """
        return ItemState(
            added_at=self.added_at,
            added_from=self.added_from,
            added_caveat=self.added_caveat,
            updated_at=self.updated_at,
            updated_from=self.updated_from,
            updated_caveat=self.updated_caveat,
            deleted_at=self.deleted_at,
            fingerprint=self.fingerprint_hash(),
        )

    def match_keys(self) -> List[str]:
        """Get the keys recognizing the item in another crawl, the most reliable first.

        Returns:
            List[str]: The keys, none for the base class.
        """
        return []
