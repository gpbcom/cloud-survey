from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, field_validator

# First Party Imports.
from models.cloud.enums import PriceModel
from models.cloud.prices.exception import (
    InvalidCoverageModelError,
    InvalidCoverageProductError,
    InvalidCoverageReasonError,
    InvalidCoverageSourceError,
    PriceCheckError,
)
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue


class CoverageStatement(BaseModel):
    """A curated statement of how a catalogue product without price of its own is charged.

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        MODELS (ClassVar[Tuple[PriceModel, ...]]): The models a statement may state.
        product (str): The catalogue product, by its name.
        model (PriceModel): Free of charge, included in another service, priced on request, or not published.
        reason (str): Why, as the evidence states it.
        source (str): The page stating it (the evidence).

    Notes:
        A free product is priced at zero, the others have no price but their reason: every catalogue product ends
        priced or explicitly unpriced.
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()
    MODELS: ClassVar[Tuple[PriceModel, ...]] = (
        PriceModel.FREE,
        PriceModel.INCLUDED,
        PriceModel.QUOTE,
        PriceModel.NOT_PUBLIC,
    )

    model_config = ConfigDict(frozen=True, extra="forbid")

    product: str = Field(description="The catalogue product.")
    model: PriceModel = Field(description="How it is charged.")
    reason: str = Field(description="Why.")
    source: str = Field(description="The page stating it.")

    @field_validator("product", mode="before")
    def validate_product(cls, value: RawValue) -> RawValue:
        """Validate the raw product name: a text of 1 to 300 characters.

        Args:
            value (RawValue): The raw product name.

        Returns:
            RawValue: The checked product name.

        Raises:
            InvalidCoverageProductError: If it is not a text of 1 to 300 characters.
        """
        try:
            return cls.CHECK.text(value, 300)
        except PriceCheckError as e:
            raise InvalidCoverageProductError(e.value, e.expected) from e

    @field_validator("model", mode="before")
    def validate_model(cls, value: RawValue) -> RawValue:
        """Validate the raw model: free, included, quote or not-public.

        Args:
            value (RawValue): The raw model.

        Returns:
            RawValue: The checked model.

        Raises:
            InvalidCoverageModelError: If it is not one of the statement models.
        """
        try:
            return cls.CHECK.choice(value, [model.value for model in cls.MODELS])
        except PriceCheckError as e:
            raise InvalidCoverageModelError(e.value, e.expected) from e

    @field_validator("reason", mode="before")
    def validate_reason(cls, value: RawValue) -> RawValue:
        """Validate the raw reason: a text of 1 to 500 characters.

        Args:
            value (RawValue): The raw reason.

        Returns:
            RawValue: The checked reason.

        Raises:
            InvalidCoverageReasonError: If it is not a text of 1 to 500 characters.
        """
        try:
            return cls.CHECK.text(value, 500)
        except PriceCheckError as e:
            raise InvalidCoverageReasonError(e.value, e.expected) from e

    @field_validator("source", mode="before")
    def validate_source(cls, value: RawValue) -> RawValue:
        """Validate the raw evidence: an http or https URL.

        Args:
            value (RawValue): The raw evidence.

        Returns:
            RawValue: The checked evidence.

        Raises:
            InvalidCoverageSourceError: If it is not an http or https URL.
        """
        try:
            return cls.CHECK.url(value)
        except PriceCheckError as e:
            raise InvalidCoverageSourceError(e.value, e.expected) from e
