from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import ClassVar, List, Tuple, Union

# Third Party Imports.
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.field_check import MarketFieldCheck


class VersionChange(BaseModel):
    """What a crawl changed in a catalogue product or a marketplace software, against its previous version.

    Attributes:
        TEXT_LIMIT (ClassVar[int]): The most characters of a value shown before or after a change.
        NAME_LIMIT (ClassVar[int]): The most characters of a field name.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        crawl_id (int): The crawl which found the version.
        recorded_at (AwareDatetime): When the crawl found the version.
        first (bool): Whether the version is the first one stored (the item first seen).
        added (List[str]): The fields the version has and the previous one has not.
        removed (List[str]): The fields the previous version has and this one has not.
        changed (List[Tuple[str, str, str]]): The fields whose value changed: the field, the value before and the
            value after, written as short texts.

    Notes:
        The values are written for display (JSON text for the lists and objects) and truncated to `TEXT_LIMIT`.
    """

    TEXT_LIMIT: ClassVar[int] = 120
    NAME_LIMIT: ClassVar[int] = 100
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    crawl_id: int = Field(ge=1, description="The crawl which found the version.")
    recorded_at: AwareDatetime = Field(description="When the crawl found the version.")
    first: bool = Field(default=False, description="Whether the item was first seen in this version.")
    added: List[str] = Field(default_factory=list, description="The fields added since the previous version.")
    removed: List[str] = Field(default_factory=list, description="The fields removed since the previous version.")
    changed: List[Tuple[str, str, str]] = Field(
        default_factory=list, description="The fields changed: the field, the value before and after."
    )

    @field_validator("crawl_id", mode="before")
    def validate_crawl_id(cls, value: JsonValue) -> JsonValue:
        """Validate the raw crawl identifier: a whole number of at least 1.

        Args:
            value (JsonValue): The raw identifier.

        Returns:
            JsonValue: The identifier.

        Raises:
            InvalidMarketNumberError: If it is not a whole number of at least 1.
        """
        return cls.CHECK.number(value, "change crawl", low=1, integer=True)

    @field_validator("recorded_at", mode="before")
    def validate_recorded_at(cls, value: Union[JsonValue, datetime]) -> Union[JsonValue, datetime]:
        """Validate the raw recording date: a date-time, or an ISO text trimmed.

        Args:
            value (Union[JsonValue, datetime]): The raw date.

        Returns:
            Union[JsonValue, datetime]: The date (its time zone is checked by pydantic afterwards).
        """
        return value.strip() if isinstance(value, str) else value

    @field_validator("first", mode="before")
    def validate_first(cls, value: JsonValue) -> JsonValue:
        """Validate the raw first-seen flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "change first seen")

    @field_validator("added", "removed", mode="before")
    def validate_fields(cls, value: JsonValue) -> JsonValue:
        """Validate the raw added or removed fields: a list of field names of 1 to 100 characters.

        Args:
            value (JsonValue): The raw names.

        Returns:
            JsonValue: The names, trimmed.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a name is not a text of that length.
        """
        return [
            cls.CHECK.text(name, "change field", cls.NAME_LIMIT)
            for name in cls.CHECK.items(value, "change fields", "field names")
        ]

    @field_validator("changed", mode="before")
    def validate_changed(cls, value: JsonValue) -> JsonValue:
        """Validate the raw changed fields: a list of (field, before, after) texts.

        Args:
            value (JsonValue): The raw changes.

        Returns:
            JsonValue: The changes, the field name trimmed (their shape is checked by pydantic afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a field name is not a text of 1 to 100 characters, or a value is not a text of
                at most `TEXT_LIMIT` characters.
        """
        changes: List[JsonValue] = []
        for change in cls.CHECK.items(value, "changed fields", "(field, before, after) texts"):
            if isinstance(change, (list, tuple)) and len(change) == 3:
                name, before, after = change
                changes.append(
                    [
                        cls.CHECK.text(name, "changed field", cls.NAME_LIMIT),
                        cls.CHECK.text(before, "value before", cls.TEXT_LIMIT, minimum=0, collapse=False),
                        cls.CHECK.text(after, "value after", cls.TEXT_LIMIT, minimum=0, collapse=False),
                    ]
                )
            else:
                changes.append(change)
        return changes
