from __future__ import annotations

# Standard Library Imports.
from typing import ClassVar, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.exception import DuplicateCompanyKeyError
from models.companies.figures.reported_company import ReportedCompany
from models.markets.field_check import MarketFieldCheck


class ReportedFigures(BaseModel):
    """The figures researched by hand from the companies' annual reports (`data/curated/figures.json`).

    Attributes:
        CHECK (ClassVar[MarketFieldCheck]): The checks of the raw fields.
        companies (List[ReportedCompany]): The researched companies, each once.

    Notes:
        They fill the years no filed source covers (before EDGAR, the companies outside the SEC, the private ones):
        a filed figure of the same line and period always wins over a researched one.
    """

    CHECK: ClassVar[MarketFieldCheck] = MarketFieldCheck()

    model_config = ConfigDict(frozen=True, extra="forbid")

    companies: List[ReportedCompany] = Field(default_factory=list, description="The researched companies.")

    @field_validator("companies", mode="before")
    def validate_companies(cls, value: JsonValue) -> JsonValue:
        """Validate the raw companies: a list (none when missing), each company once.

        Args:
            value (JsonValue): The raw companies.

        Returns:
            JsonValue: The companies (validated by their model afterwards).

        Raises:
            InvalidMarketListError: If it is not a list.
            DuplicateCompanyKeyError: If a company is researched twice.
        """
        if value is None:
            return []
        items = cls.CHECK.items(value, "reported companies", "mappings of company, currency and years")
        seen: List[str] = []
        for item in items:
            key = item.get("company") if isinstance(item, dict) else None
            if isinstance(key, str):
                if key in seen:
                    raise DuplicateCompanyKeyError("reported company", key)
                seen.append(key)
        return items

    ############################
    # Publicly Exposed Methods #
    ############################

    def of(self, company: str) -> Optional[ReportedCompany]:
        """Get the researched figures of a company.

        Args:
            company (str): The company.

        Returns:
            Optional[ReportedCompany]: Its figures, `None` when it was not researched.
        """
        return next((entry for entry in self.companies if entry.company == company), None)
