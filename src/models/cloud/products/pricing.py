from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import PricingPolicy
from models.cloud.exception import EmptyCurrencyError, InvalidPricingPolicyError, NegativeAmountError


class ServicePricingPolicy(BaseModel):
    """Cloud service pricing policy.

    Attributes:
        pricing_policy (PricingPolicy): The current cloud service's pricing policy.
        free_limit (float): The amount above which the user starts paying.
        amount (float): The amount billed above the free limit.
        currency (str): The currency symbol.
    """

    pricing_policy: PricingPolicy = Field(description="Defines on which base the user will be billed.")
    free_limit: float = Field(description="Usage above which the user will start getting billed.")
    amount: float = Field(description="Billing value per resource/artifact.")
    currency: str = Field(description="Standardized currency code.")

    @field_validator("pricing_policy", mode="before")
    def validate_pricing_policy(cls, value: JsonValue) -> PricingPolicy:
        """Validate the raw pricing policy.

        Args:
            value (JsonValue): The raw pricing policy input.

        Returns:
            PricingPolicy: The validated pricing policy extracted from scraping.

        Raises:
            InvalidPricingPolicyError: In case of invalid pricing policy.
        """
        if not isinstance(value, str):
            raise InvalidPricingPolicyError(str(value))
        try:
            return PricingPolicy(value)
        except ValueError as e:
            raise InvalidPricingPolicyError(str(value)) from e

    @field_validator("free_limit", "amount", mode="before")
    def validate_numbers(cls, value: JsonValue) -> JsonValue:
        """Validate the raw float number fields.

        Args:
            value (JsonValue): The raw scraping input value.

        Returns:
            JsonValue: The unchanged value.

        Raises:
            NegativeAmountError: In case of value less than 0.
        """
        if not isinstance(value, (int, float, str)):
            return value
        try:
            number = float(value)
        except ValueError:
            return value
        if number < 0:
            raise NegativeAmountError(number)
        return value

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: JsonValue) -> JsonValue:
        """Validate the raw currency symbol field.

        Args:
            value (JsonValue): The raw scraping currency input.

        Returns:
            JsonValue: The unchanged value, its type is checked by pydantic afterwards.

        Raises:
            EmptyCurrencyError: If the currency symbol is missing or empty.
        """
        if value is None or value == "":
            raise EmptyCurrencyError()
        return value
