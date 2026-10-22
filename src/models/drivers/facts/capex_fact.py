from __future__ import annotations

# Standard Library Imports.
from datetime import date

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.drivers.exception import InvalidFactPeriodError


class CapexFact(BaseModel):
    """A capital expenditure fact of a filing, as SEC EDGAR publishes it (`companyfacts`, in US dollars).

    Attributes:
        provider (CloudProvider): The provider of the filing group.
        concept (str): The US-GAAP concept, e.g. `PaymentsToAcquirePropertyPlantAndEquipment`.
        start (date): The first day of the period (the fiscal year to date in a 10-Q).
        end (date): The last day of the period.
        value (float): The dollars spent over the period.
        form (str): The filing form, e.g. `10-Q`.
        source_url (str): The `companyfacts` document read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The provider of the filing group.")
    concept: str = Field(min_length=1, description="The US-GAAP concept.")
    start: date = Field(description="The first day of the period.")
    end: date = Field(description="The last day of the period.")
    value: float = Field(ge=0, description="The dollars spent over the period.")
    form: str = Field(min_length=1, description="The filing form.")
    source_url: str = Field(min_length=1, max_length=2048, description="The document read.")

    @field_validator("concept", "form", "source_url", mode="before")
    def validate_text(cls, value: JsonValue) -> JsonValue:
        """Validate a raw text: trimmed.

        Args:
            value (JsonValue): The raw text.

        Returns:
            JsonValue: The text, trimmed.
        """
        return value.strip() if isinstance(value, str) else value

    @field_validator("end", mode="before")
    def validate_end(cls, value: JsonValue, info: ValidationInfo) -> JsonValue:
        """Validate the raw last day: not before the first one.

        Args:
            value (JsonValue): The raw last day, written `YYYY-MM-DD`.
            info (ValidationInfo): The fields validated so far (the first day).

        Returns:
            JsonValue: The last day (parsed by pydantic afterwards).

        Raises:
            InvalidFactPeriodError: If it comes before the first day.
        """
        start = info.data.get("start")
        if isinstance(value, str) and isinstance(start, date):
            try:
                end = date.fromisoformat(value.strip())
            except ValueError:
                return value
            if end < start:
                raise InvalidFactPeriodError(start.isoformat(), end.isoformat())
        return value
