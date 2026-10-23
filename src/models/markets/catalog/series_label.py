from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.markets.enums import ShareSource
from models.markets.exception import InvalidMarketValueError
from models.markets.field_check import MarketFieldCheck


class SeriesLabel(BaseModel):
    """The company behind a label of a share source, e.g. StatCounter's `Chrome` is Google.

    Attributes:
        KEY (ClassVar[Pattern[str]]): The format of a company key: lower-case words joined by hyphens.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        source (ShareSource): The source printing the label.
        label (str): The label, exactly as the source prints it (`bing`, `YANDEX RU`).
        company (str): The company of the chronology it belongs to.

    Notes:
        A label without a company (`Linux`, `Unknown`, a small engine) is stored as printed, without a company, and
        the charts count it in "Others".
    """

    KEY: ClassVar[Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: ShareSource = Field(default=ShareSource.STATCOUNTER, description="The source printing the label.")
    label: str = Field(min_length=1, max_length=80, description="The label, as printed.")
    company: str = Field(description="The company it belongs to.")

    @field_validator("source", mode="before")
    def validate_source(cls, value: JsonValue) -> JsonValue:
        """Validate the raw source: a `ShareSource` value.

        Args:
            value (JsonValue): The raw source.

        Returns:
            JsonValue: The source.

        Raises:
            InvalidMarketChoiceError: If it is not a known share source.
        """
        return cls.CHECK.choice(value, "label source", [source.value for source in ShareSource])

    @field_validator("label", mode="before")
    def validate_label(cls, value: JsonValue) -> JsonValue:
        """Validate the raw label: a text of 1 to 80 characters, trimmed (its case is kept, labels match exactly).

        Args:
            value (JsonValue): The raw label.

        Returns:
            JsonValue: The label.

        Raises:
            InvalidMarketTextError: If it is not a text of 1 to 80 characters.
        """
        return cls.CHECK.text(value, "source label", 80, collapse=False)

    @field_validator("company", mode="before")
    def validate_company(cls, value: JsonValue) -> JsonValue:
        """Validate the raw company: a key of the chronology.

        Args:
            value (JsonValue): The raw company.

        Returns:
            JsonValue: The company key, trimmed.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidMarketValueError: If it is not lower-case words joined by hyphens.
        """
        key = cls.CHECK.text(value, "company key", 40) or ""
        if not cls.KEY.match(key):
            raise InvalidMarketValueError("company key", key, "lower-case words joined by hyphens")
        return key
