from __future__ import annotations

# Standard Library Imports.
import re
from typing import Dict, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.classification.category_hint import CategoryHint
from models.classification.exception import IncompleteRulesError, InvalidRulePatternError
from models.classification.type_rule import TypeRule
from models.cloud.enums import DeliveryMethod, SoftwareCategory, SoftwareType


class ClassificationRules(BaseModel):
    """Rules classifying the marketplace software into categories and types (`conf/classification.yaml`).

    Attributes:
        type_categories (Dict[SoftwareType, List[SoftwareCategory]]): The categories of each type, every type covered.
        delivery_categories (Dict[DeliveryMethod, List[SoftwareCategory]]): The category of a software of unknown
            type, by delivery method, every delivery method covered.
        category_hints (List[CategoryHint]): The marketplace categories directly giving a category.
        name_rules (List[TypeRule]): The types of the well-known products, given by their name before anything else.
        packaging_suffix (Optional[str]): The case-insensitive pattern of the packaging suffix of the names, removed
            before matching them, e.g. ` on Ubuntu 24.04`.
        category_rules (List[TypeRule]): The types given by the marketplace categories.
        keyword_rules (List[TypeRule]): The types given by the software name, else by its description.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type_categories: Dict[SoftwareType, List[SoftwareCategory]] = Field(description="The categories of each type.")
    delivery_categories: Dict[DeliveryMethod, List[SoftwareCategory]] = Field(
        description="The category of a software of unknown type, by delivery method."
    )
    category_hints: List[CategoryHint] = Field(default_factory=list, description="The category hints.")
    name_rules: List[TypeRule] = Field(default_factory=list, description="The well-known product rules.")
    packaging_suffix: Optional[str] = Field(default=None, description="The packaging suffix of the names.")
    category_rules: List[TypeRule] = Field(default_factory=list, description="The marketplace category rules.")
    keyword_rules: List[TypeRule] = Field(default_factory=list, description="The name and description rules.")

    @field_validator("packaging_suffix", mode="before")
    def validate_packaging_suffix(cls, value: JsonValue) -> JsonValue:
        """Validate the raw packaging suffix pattern.

        Args:
            value (JsonValue): The raw pattern.

        Returns:
            JsonValue: The unchanged pattern (its type is checked by pydantic afterwards).

        Raises:
            InvalidRulePatternError: If the pattern is not a valid regular expression.
        """
        if isinstance(value, str):
            try:
                re.compile(value)
            except re.error as e:
                raise InvalidRulePatternError(value, str(e)) from e
        return value

    @field_validator("type_categories", mode="before")
    def validate_type_categories(cls, value: JsonValue) -> JsonValue:
        """Validate that every software type has its categories.

        Args:
            value (JsonValue): The raw mapping.

        Returns:
            JsonValue: The unchanged mapping (its content is checked by pydantic afterwards).

        Raises:
            IncompleteRulesError: If a software type has no entry.
        """
        missing = [str(kind) for kind in SoftwareType if isinstance(value, dict) and kind.value not in value]
        if missing:
            raise IncompleteRulesError("type_categories", missing)
        return value

    @field_validator("delivery_categories", mode="before")
    def validate_delivery_categories(cls, value: JsonValue) -> JsonValue:
        """Validate that every delivery method has a category.

        Args:
            value (JsonValue): The raw mapping.

        Returns:
            JsonValue: The unchanged mapping (its content is checked by pydantic afterwards).

        Raises:
            IncompleteRulesError: If a delivery method has no entry.
        """
        missing = [str(method) for method in DeliveryMethod if isinstance(value, dict) and method.value not in value]
        if missing:
            raise IncompleteRulesError("delivery_categories", missing)
        return value
