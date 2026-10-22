from __future__ import annotations

# Standard Library Imports.
import re
from typing import Dict, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.classification.audience_hint import AudienceHint
from models.classification.category_rule import CategoryRule
from models.classification.exception import IncompleteRulesError, InvalidRulePatternError
from models.cloud.enums import DeliveryMethod, SoftwareCategory


class ClassificationRules(BaseModel):
    """Rules classifying the products and the marketplace software into the taxonomy (`conf/classification.yaml`).

    Attributes:
        delivery_audiences (Dict[DeliveryMethod, List[SoftwareCategory]]): Who a software of unknown audience is meant
            for, by delivery method, every delivery method covered.
        product_audiences (List[SoftwareCategory]): Who a catalogue product of unknown audience is meant for.
        audience_hints (List[AudienceHint]): The source labels directly telling the audience.
        delivery_categories (Dict[DeliveryMethod, List[str]]): The categories of a software nothing else classifies,
            by delivery method (e.g. a virtual machine image), no category when a method is missing.
        noise_labels (List[str]): The case-insensitive patterns of the source labels which are not categories (a
            "Products" tab, "Other"), matched on the whole label.
        name_rules (List[CategoryRule]): The categories of the well-known products, given by their name first.
        packaging_suffix (Optional[str]): The case-insensitive pattern of the packaging suffix of the names, removed
            before matching them, e.g. ` on Ubuntu 24.04`.
        category_rules (List[CategoryRule]): The categories given by the source labels.
        keyword_rules (List[CategoryRule]): The categories given by the name, else by the description.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    delivery_audiences: Dict[DeliveryMethod, List[SoftwareCategory]] = Field(
        description="Who a software of unknown audience is meant for, by delivery method."
    )
    product_audiences: List[SoftwareCategory] = Field(
        default_factory=list, description="Who a catalogue product of unknown audience is meant for."
    )
    audience_hints: List[AudienceHint] = Field(default_factory=list, description="The audience hints.")
    delivery_categories: Dict[DeliveryMethod, List[str]] = Field(
        default_factory=dict, description="The categories of a software nothing else classifies, by delivery method."
    )
    noise_labels: List[str] = Field(default_factory=list, description="The source labels which are not categories.")
    name_rules: List[CategoryRule] = Field(default_factory=list, description="The well-known product rules.")
    packaging_suffix: Optional[str] = Field(default=None, description="The packaging suffix of the names.")
    category_rules: List[CategoryRule] = Field(default_factory=list, description="The source label rules.")
    keyword_rules: List[CategoryRule] = Field(default_factory=list, description="The name and description rules.")

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

    @field_validator("noise_labels", mode="before")
    def validate_noise_labels(cls, value: JsonValue) -> JsonValue:
        """Validate the raw noise label patterns.

        Args:
            value (JsonValue): The raw patterns.

        Returns:
            JsonValue: The patterns without duplicates (their type is checked by pydantic afterwards), an empty list
                when missing.

        Raises:
            InvalidRulePatternError: If a pattern is not a valid regular expression.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        for pattern in value:
            if isinstance(pattern, str):
                try:
                    re.compile(pattern)
                except re.error as e:
                    raise InvalidRulePatternError(pattern, str(e)) from e
        return list(dict.fromkeys(pattern for pattern in value if isinstance(pattern, str)))

    @field_validator("product_audiences", mode="before")
    def validate_product_audiences(cls, value: JsonValue) -> JsonValue:
        """Validate the audiences of the products of unknown audience: a list, duplicates dropped.

        Args:
            value (JsonValue): The raw audiences.

        Returns:
            JsonValue: The audiences in their order, without duplicates (their values are checked by pydantic
                afterwards), an empty list when missing.
        """
        if value is None:
            return []
        if isinstance(value, list):
            return list(dict.fromkeys(item for item in value if isinstance(item, str)))
        return value

    @field_validator("delivery_audiences", mode="before")
    def validate_delivery_audiences(cls, value: JsonValue) -> JsonValue:
        """Validate that every delivery method has an audience.

        Args:
            value (JsonValue): The raw mapping.

        Returns:
            JsonValue: The unchanged mapping (its content is checked by pydantic afterwards).

        Raises:
            IncompleteRulesError: If a delivery method has no entry.
        """
        missing = [str(method) for method in DeliveryMethod if isinstance(value, dict) and method.value not in value]
        if missing:
            raise IncompleteRulesError("delivery_audiences", missing)
        return value
