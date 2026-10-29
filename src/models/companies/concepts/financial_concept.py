from __future__ import annotations

# Standard Library Imports.
import re
from typing import ClassVar, List, Pattern

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.enums import FinancialMetric, FinancialNature
from models.companies.exception import InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class FinancialConcept(BaseModel):
    """The XBRL concepts standing for a statement line, the preferred one first.

    Attributes:
        CONCEPT (ClassVar[Pattern[str]]): The format of a concept: `taxonomy:Name`, e.g. `us-gaap:Revenues`.
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        metric (FinancialMetric): The statement line.
        nature (FinancialNature): How it adds up over time (a flow, a balance, a per-share figure).
        concepts (List[str]): The concepts filed for it, the preferred one first (`us-gaap`, `ifrs-full`, `dei`).
        negate (bool): Whether the filed value is the opposite of the stored one (a cash outflow filed negative).

    Notes:
        A company reporting a line under several concepts over the years (a change of accounting standard, a new
        revenue concept from 2018) has each period read from the first concept filing it, the later concepts
        filling the periods the first lacks.
    """

    CONCEPT: ClassVar[Pattern[str]] = re.compile(r"^(us-gaap|ifrs-full|dei|srt):[A-Za-z][A-Za-z0-9]{2,150}$")
    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: FinancialMetric = Field(description="The statement line.")
    nature: FinancialNature = Field(description="How it adds up over time.")
    concepts: List[str] = Field(min_length=1, description="The concepts filed for it, the preferred one first.")
    negate: bool = Field(default=False, description="Whether the filed value is the opposite of the stored one.")

    @field_validator("metric", mode="before")
    def validate_metric(cls, value: JsonValue) -> JsonValue:
        """Validate the raw statement line: one of the financial metrics.

        Args:
            value (JsonValue): The raw line.

        Returns:
            JsonValue: The line.

        Raises:
            InvalidMarketChoiceError: If it is not a financial metric.
        """
        return cls.CHECK.choice(value, "statement line", [metric.value for metric in FinancialMetric])

    @field_validator("nature", mode="before")
    def validate_nature(cls, value: JsonValue) -> JsonValue:
        """Validate the raw nature: flow, balance or per-share.

        Args:
            value (JsonValue): The raw nature.

        Returns:
            JsonValue: The nature.

        Raises:
            InvalidMarketChoiceError: If it is not a financial nature.
        """
        return cls.CHECK.choice(value, "statement line nature", [nature.value for nature in FinancialNature])

    @field_validator("concepts", mode="before")
    def validate_concepts(cls, value: JsonValue) -> JsonValue:
        """Validate the raw concepts: `taxonomy:Name` texts, each once.

        Args:
            value (JsonValue): The raw concepts.

        Returns:
            JsonValue: The concepts, each once in their order.

        Raises:
            InvalidMarketListError: If it is not a list.
            InvalidMarketTextError: If a concept is not a text.
            InvalidCompanyValueError: If a concept is not written `taxonomy:Name`.
        """
        concepts: List[JsonValue] = []
        for item in cls.CHECK.items(value, "XBRL concepts", "taxonomy:Name texts"):
            concept = cls.CHECK.text(item, "XBRL concept", 160, collapse=False) or ""
            if not cls.CONCEPT.match(concept):
                raise InvalidCompanyValueError("XBRL concept", concept, "taxonomy:Name (us-gaap, ifrs-full, dei, srt)")
            if concept not in concepts:
                concepts.append(concept)
        return concepts

    @field_validator("negate", mode="before")
    def validate_negate(cls, value: JsonValue) -> JsonValue:
        """Validate the raw sign flag: a boolean.

        Args:
            value (JsonValue): The raw flag.

        Returns:
            JsonValue: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        return cls.CHECK.flag(value, "negated concept")
