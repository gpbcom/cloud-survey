from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.companies.enums import PatentCitationKind
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class PatentCitation(BaseModel):
    """A citation read on a publication page: another publication it cites, or that cites it.

    Attributes:
        PUBLICATION (ClassVar[Pattern[str]]): The format of a publication number, e.g. `US10000000B2`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        publication_number (str): The other publication.
        kind (PatentCitationKind): Which way the citation goes, and whether it is the family's.
        examiner (bool): Whether the examiner added it (marked `*` by Google Patents).
        priority_date (Optional[date]): The priority date of the other publication.
        publication_date (Optional[date]): The publication date of the other publication.
        assignee (Optional[str]): The assignee of the other publication, as Google Patents writes it.
        title (Optional[str]): The title of the other publication.
    """

    PUBLICATION: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{2}[A-Z0-9]{1,24}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    publication_number: str = Field(description="The other publication.")
    kind: PatentCitationKind = Field(description="Which way the citation goes.")
    examiner: bool = Field(default=False, description="Whether the examiner added it.")
    priority_date: Optional[date] = Field(default=None, description="The priority date of the other one.")
    publication_date: Optional[date] = Field(default=None, description="The publication date of the other one.")
    assignee: Optional[str] = Field(default=None, max_length=300, description="The assignee of the other one.")
    title: Optional[str] = Field(default=None, max_length=1000, description="The title of the other one.")

    @field_validator("publication_number", mode="before")
    def validate_publication_number(cls, value: JsonValue) -> JsonValue:
        """Validate the raw publication: an office code then letters and digits, separators removed.

        Args:
            value (JsonValue): The raw publication, e.g. `US-10000000-B2`.

        Returns:
            JsonValue: The publication, e.g. `US10000000B2`.

        Raises:
            InvalidMarketTextError: If it is not a text.
            InvalidCompanyValueError: If it is not an office code followed by letters and digits.
        """
        number = (cls.CHECK.text(value, "cited publication", 40) or "").replace("-", "").replace(" ", "").upper()
        if not cls.PUBLICATION.match(number):
            raise InvalidCompanyValueError("cited publication", number, "an office code followed by letters and digits")
        return number

    @field_validator("kind", mode="before")
    def validate_kind(cls, value: JsonValue) -> JsonValue:
        """Validate the raw direction: one of the citation kinds.

        Args:
            value (JsonValue): The raw kind.

        Returns:
            JsonValue: The kind.

        Raises:
            InvalidMarketChoiceError: If it is not a citation kind.
        """
        return cls.CHECK.choice(value, "citation kind", [kind.value for kind in PatentCitationKind])

    @field_validator("examiner", mode="before")
    def validate_examiner(cls, value: JsonValue) -> JsonValue:
        """Validate the raw examiner flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "examiner citation")

    @field_validator("priority_date", "publication_date", mode="before")
    def validate_day(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw date: a date, or none.

        Args:
            value (JsonValue): The raw date.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The date, `YYYY-MM-DD`, `None` when missing.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        return cls.CHECK.iso_day(value, f"cited {info.field_name}", optional=True)

    @field_validator("assignee", "title", mode="before")
    def validate_text(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate a raw text: trimmed, at most 1000 characters, or none.

        Args:
            value (JsonValue): The raw text.
            info (ValidationInfo): The field validated.

        Returns:
            JsonValue: The text, cut to its field's length, `None` when blank.

        Raises:
            InvalidMarketTextError: If it is neither missing nor a text.
        """
        limit = 300 if info.field_name == "assignee" else 1000
        text = cls.CHECK.text(
            value[:limit] if isinstance(value, str) else value, f"cited {info.field_name}", limit, optional=True
        )
        return text
