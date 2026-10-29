from __future__ import annotations

# Standard Library Imports.
from decimal import Decimal
from typing import ClassVar, Dict, FrozenSet, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.cloud.enums import PriceModel, PriceTerm, PriceUnit
from models.cloud.prices.exception import (
    InvalidConceptError,
    InvalidFamilyError,
    InvalidLabelError,
    InvalidMinimumsError,
    InvalidModelError,
    InvalidOsError,
    InvalidQuantityError,
    InvalidTermError,
    InvalidUnitError,
    PriceCheckError,
)
from models.cloud.prices.price_field_check import PriceFieldCheck, RawValue


class UsageItem(BaseModel):
    """A consumption of a usage profile: a quantity of a unit of a kind of service, per month.

    Attributes:
        CHECK (ClassVar[PriceFieldCheck]): The checks of the raw fields (each field raises its own error).
        label (str): What it stands for, e.g. `Web servers`.
        concept (Optional[str]): The service concept priced (a concept of the Correspondences tab), if any.
        family (Optional[str]): The price family priced instead (compute instance, storage...), if no concept.
        unit (PriceUnit): The unit of the quantity.
        quantity (Decimal): The quantity per month, in `unit`.
        minimums (Dict[str, Decimal]): The least value of the typed attributes of a candidate (`vcpu`,
            `memory_gib`, `storage_gib`).
        os (Optional[str]): The operating system or engine required, if any.
        model (PriceModel): The pricing model wanted.
        term (PriceTerm): The commitment term wanted.
        ATTRIBUTES (ClassVar[FrozenSet[str]]): The typed attributes a minimum may name.
    """

    CHECK: ClassVar[PriceFieldCheck] = PriceFieldCheck()
    ATTRIBUTES: ClassVar[FrozenSet[str]] = frozenset({"vcpu", "memory_gib", "storage_gib"})

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(description="What it stands for.")
    concept: Optional[str] = Field(default=None, description="The service concept priced.")
    family: Optional[str] = Field(default=None, description="The price family priced.")
    unit: PriceUnit = Field(description="The unit of the quantity.")
    quantity: Decimal = Field(description="The quantity per month.")
    minimums: Dict[str, Decimal] = Field(default_factory=dict, description="The least attributes of a candidate.")
    os: Optional[str] = Field(default=None, description="The operating system required.")
    model: PriceModel = Field(default=PriceModel.ON_DEMAND, description="The pricing model wanted.")
    term: PriceTerm = Field(default=PriceTerm.NONE, description="The commitment term wanted.")

    @field_validator("label", mode="before")
    def validate_label(cls, value: RawValue) -> RawValue:
        """Validate the raw usage label: a text of 1 to 120 characters.

        Args:
            value (RawValue): The raw usage label.

        Returns:
            RawValue: The checked usage label.

        Raises:
            InvalidLabelError: If it is not a text of 1 to 120 characters.
        """
        try:
            return cls.CHECK.text(value, 120)
        except PriceCheckError as e:
            raise InvalidLabelError(e.value, e.expected) from e

    @field_validator("concept", mode="before")
    def validate_concept(cls, value: RawValue) -> RawValue:
        """Validate the raw service concept: a text of 1 to 200 characters, or nothing.

        Args:
            value (RawValue): The raw service concept.

        Returns:
            RawValue: The checked service concept.

        Raises:
            InvalidConceptError: If it is not a text of 1 to 200 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 200, optional=True)
        except PriceCheckError as e:
            raise InvalidConceptError(e.value, e.expected) from e

    @field_validator("family", mode="before")
    def validate_family(cls, value: RawValue) -> RawValue:
        """Validate the raw price family: a text of 1 to 200 characters, or nothing.

        Args:
            value (RawValue): The raw price family.

        Returns:
            RawValue: The checked price family.

        Raises:
            InvalidFamilyError: If it is not a text of 1 to 200 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 200, optional=True)
        except PriceCheckError as e:
            raise InvalidFamilyError(e.value, e.expected) from e

    @field_validator("unit", mode="before")
    def validate_unit(cls, value: RawValue) -> RawValue:
        """Validate the raw unit: a `PriceUnit` value.

        Args:
            value (RawValue): The raw unit.

        Returns:
            RawValue: The checked unit.

        Raises:
            InvalidUnitError: If it is not a `PriceUnit` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceUnit])
        except PriceCheckError as e:
            raise InvalidUnitError(e.value, e.expected) from e

    @field_validator("quantity", mode="before")
    def validate_quantity(cls, value: RawValue) -> RawValue:
        """Validate the raw quantity: a number from 0.

        Args:
            value (RawValue): The raw quantity.

        Returns:
            RawValue: The checked quantity.

        Raises:
            InvalidQuantityError: If it is not a number from 0.
        """
        try:
            return cls.CHECK.number(value)
        except PriceCheckError as e:
            raise InvalidQuantityError(e.value, e.expected) from e

    @field_validator("os", mode="before")
    def validate_os(cls, value: RawValue) -> RawValue:
        """Validate the raw operating system: a text of 1 to 120 characters, or nothing.

        Args:
            value (RawValue): The raw operating system.

        Returns:
            RawValue: The checked operating system.

        Raises:
            InvalidOsError: If it is not a text of 1 to 120 characters, or nothing.
        """
        try:
            return cls.CHECK.text(value, 120, optional=True)
        except PriceCheckError as e:
            raise InvalidOsError(e.value, e.expected) from e

    @field_validator("model", mode="before")
    def validate_model(cls, value: RawValue) -> RawValue:
        """Validate the raw pricing model: a `PriceModel` value.

        Args:
            value (RawValue): The raw pricing model.

        Returns:
            RawValue: The checked pricing model.

        Raises:
            InvalidModelError: If it is not a `PriceModel` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceModel])
        except PriceCheckError as e:
            raise InvalidModelError(e.value, e.expected) from e

    @field_validator("term", mode="before")
    def validate_term(cls, value: RawValue) -> RawValue:
        """Validate the raw commitment term: a `PriceTerm` value.

        Args:
            value (RawValue): The raw commitment term.

        Returns:
            RawValue: The checked commitment term.

        Raises:
            InvalidTermError: If it is not a `PriceTerm` value.
        """
        try:
            return cls.CHECK.choice(value, [member.value for member in PriceTerm])
        except PriceCheckError as e:
            raise InvalidTermError(e.value, e.expected) from e

    @field_validator("minimums", mode="before")
    def validate_minimums(cls, value: RawValue) -> RawValue:
        """Validate the raw attribute minimums: an object of typed attributes and their least values.

        Args:
            value (RawValue): The raw minimums.

        Returns:
            RawValue: The checked minimums.

        Raises:
            InvalidMinimumsError: If it is not an object, names another attribute, or a value is not a number from 0.
        """
        checked: Dict[str, JsonValue] = {}
        try:
            for name, raw in cls.CHECK.mapping(value).items():
                if name not in cls.ATTRIBUTES:
                    raise InvalidMinimumsError(name, "one of " + ", ".join(sorted(cls.ATTRIBUTES)))
                checked[name] = str(cls.CHECK.number(raw))
        except PriceCheckError as e:
            raise InvalidMinimumsError(e.value, e.expected) from e
        return checked
