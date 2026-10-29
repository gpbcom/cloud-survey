from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.compounding.enums import FoundationSource, Specification


class CompoundingQuery(BaseModel):
    """What a compounding analysis fits.

    Attributes:
        providers (List[CloudProvider]): Only these providers (each fitted, and pooled), every provider of the
            configuration when empty.
        specification (Specification): The controls held constant.
        lag (int): The years the foundations are held before the entry.
        source (FoundationSource): Where the foundations come from.
    """

    model_config = ConfigDict(frozen=True)

    providers: List[CloudProvider] = Field(default_factory=list, description="Only these providers.")
    specification: Specification = Field(default=Specification.BASE, description="The controls held constant.")
    lag: int = Field(default=1, ge=1, le=5, description="The years the foundations are held.")
    source: FoundationSource = Field(default=FoundationSource.CURATED, description="Where foundations come from.")

    @field_validator("providers", mode="before")
    def validate_providers(cls, value: JsonValue) -> JsonValue:
        """Validate the raw providers: each once, in their order.

        Args:
            value (JsonValue): The raw providers.

        Returns:
            JsonValue: The providers, each once (checked by pydantic afterwards).
        """
        if isinstance(value, list):
            unique: List[JsonValue] = [*dict.fromkeys(str(item) for item in value)]
            return unique
        return value
