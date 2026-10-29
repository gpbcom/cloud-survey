from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.concepts.financial_concept import FinancialConcept
from models.companies.concepts.schedules.schedule_layout import ScheduleLayout
from models.companies.concepts.statement_layout import StatementLayout
from models.companies.enums import FinancialMetric, FinancialNature
from models.companies.exception import DuplicateCompanyKeyError, InvalidCompanyValueError
from models.markets.field_check import MarketFieldCheck


class FinancialConcepts(BaseModel):
    """How the statement lines are read: the XBRL concepts of the filings and the positions of Google Finance.

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        concepts (List[FinancialConcept]): The concepts of each statement line read from the filings.
        google_finance (StatementLayout): The positions of the statement lines on Google Finance.
        fds (ScheduleLayout): The tags of the SEC financial data schedules (EX-27, 1993 to 2001).
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    concepts: List[FinancialConcept] = Field(default_factory=list, description="The concepts of each line.")
    google_finance: StatementLayout = Field(default_factory=StatementLayout, description="The Google positions.")
    fds: ScheduleLayout = Field(default_factory=ScheduleLayout, description="The tags of the data schedules.")

    @field_validator("concepts", mode="before")
    def validate_concepts(cls, value: JsonValue) -> JsonValue:
        """Validate the raw concepts: a list, each statement line once, each concept standing for one line only.

        Args:
            value (JsonValue): The raw concepts.

        Returns:
            JsonValue: The concepts (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompanyKeyError: If a statement line or a concept is defined twice.
        """
        items = cls.CHECK.items(value, "financial concepts", "mappings of metric, nature and concepts")
        metrics: List[str] = []
        names: List[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            metric = item.get("metric")
            if isinstance(metric, str):
                if metric in metrics:
                    raise DuplicateCompanyKeyError("financial concept line", metric)
                metrics.append(metric)
            concepts = item.get("concepts")
            for concept in concepts if isinstance(concepts, list) else []:
                if isinstance(concept, str):
                    if concept in names:
                        raise DuplicateCompanyKeyError("XBRL concept", concept)
                    names.append(concept)
        return items

    @field_validator("google_finance", mode="before")
    def validate_google_finance(cls, value: JsonValue) -> JsonValue:
        """Validate the raw Google positions: a mapping, none meaning the defaults.

        Args:
            value (JsonValue): The raw positions.

        Returns:
            JsonValue: The positions (validated by their model afterwards).

        Raises:
            InvalidCompanyValueError: If it is neither missing nor a mapping.
        """
        if value is None:
            return {}
        if not isinstance(value, (dict, StatementLayout)):
            raise InvalidCompanyValueError("Google Finance layout", repr(value), "a mapping")
        return value

    @field_validator("fds", mode="before")
    def validate_fds(cls, value: JsonValue) -> JsonValue:
        """Validate the raw data schedule tags: a mapping, none meaning no tag read.

        Args:
            value (JsonValue): The raw tags.

        Returns:
            JsonValue: The tags (validated by their model afterwards).

        Raises:
            InvalidCompanyValueError: If it is neither missing nor a mapping.
        """
        if value is None:
            return {}
        if not isinstance(value, (dict, ScheduleLayout)):
            raise InvalidCompanyValueError("financial data schedule layout", repr(value), "a mapping")
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def by_concept(self) -> Dict[str, Tuple[FinancialConcept, int]]:
        """Get the statement line of each concept, and its rank among the line's concepts.

        Returns:
            Dict[str, Tuple[FinancialConcept, int]]: The line and the rank (0 for the preferred) of each concept.
        """
        return {name: (concept, rank) for concept in self.concepts for rank, name in enumerate(concept.concepts)}

    def nature(self, metric: FinancialMetric) -> Optional[FinancialNature]:
        """Get how a statement line adds up over time.

        Args:
            metric (FinancialMetric): The line.

        Returns:
            Optional[FinancialNature]: Its nature, `None` when the line is not defined.
        """
        return next((concept.nature for concept in self.concepts if concept.metric is metric), None)
