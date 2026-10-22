from __future__ import annotations

# Standard Library Imports.
from typing import List

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import CloudProvider


class NetworkFact(BaseModel):
    """A network of a provider at PeeringDB: the internet exchanges and the facilities it is linked to.

    Attributes:
        provider (CloudProvider): The provider.
        asn (int): The autonomous system of the network.
        exchanges (List[int]): The PeeringDB identifiers of the exchanges it peers at, each once.
        facilities (List[int]): The PeeringDB identifiers of the facilities it is present at, each once.
        source_url (str): The document read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: CloudProvider = Field(description="The provider.")
    asn: int = Field(gt=0, description="The autonomous system.")
    exchanges: List[int] = Field(default_factory=list, description="The exchanges it peers at.")
    facilities: List[int] = Field(default_factory=list, description="The facilities it is present at.")
    source_url: str = Field(min_length=1, max_length=2048, description="The document read.")

    @field_validator("exchanges", "facilities", mode="before")
    def validate_identifiers(cls, value: JsonValue) -> JsonValue:
        """Validate raw identifiers: each once, in their order.

        Args:
            value (JsonValue): The raw identifiers.

        Returns:
            JsonValue: The identifiers, each once (checked by pydantic afterwards).
        """
        if not isinstance(value, list):
            return value
        unique: List[JsonValue] = [*dict.fromkeys(value)] if all(isinstance(item, int) for item in value) else value
        return unique

    @field_validator("source_url", mode="before")
    def validate_source_url(cls, value: JsonValue) -> JsonValue:
        """Validate the raw document: trimmed.

        Args:
            value (JsonValue): The raw document.

        Returns:
            JsonValue: The document, trimmed.
        """
        return value.strip() if isinstance(value, str) else value
