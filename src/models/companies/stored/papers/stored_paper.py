from __future__ import annotations

# Standard Library Imports.
from datetime import date
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

# First Party Imports.
from models.companies.papers.paper_authorship import PaperAuthorship


class StoredPaper(BaseModel):
    """A stored research paper, as the Patents & Papers tab lists it (with its authors in the detail pane).

    Attributes:
        openalex_id (str): The OpenAlex work.
        companies (List[str]): The companies whose institutions it is affiliated with.
        doi (Optional[str]): Its DOI.
        title (Optional[str]): Its title.
        publication_year (Optional[int]): The year it was published.
        publication_date (Optional[date]): The day it was published.
        type (Optional[str]): Its type.
        venue (Optional[str]): Where it appeared.
        cited_by_count (int): The citations it received.
        fwci (Optional[float]): Its field-weighted citation impact.
        is_oa (bool): Whether it is open access.
        topic (Optional[str]): Its main topic.
        source_url (Optional[str]): The request it was read from.
        authors (List[PaperAuthorship]): Its authors (read for one paper only).
    """

    model_config = ConfigDict(frozen=True)

    openalex_id: str = Field(min_length=1, description="The OpenAlex work.")
    companies: List[str] = Field(default_factory=list, description="The companies.")
    doi: Optional[str] = Field(default=None, description="Its DOI.")
    title: Optional[str] = Field(default=None, description="Its title.")
    publication_year: Optional[int] = Field(default=None, description="The year it was published.")
    publication_date: Optional[date] = Field(default=None, description="The day it was published.")
    type: Optional[str] = Field(default=None, description="Its type.")
    venue: Optional[str] = Field(default=None, description="Where it appeared.")
    cited_by_count: int = Field(default=0, ge=0, description="The citations it received.")
    fwci: Optional[float] = Field(default=None, ge=0, description="Its field-weighted citation impact.")
    is_oa: bool = Field(default=False, description="Whether it is open access.")
    topic: Optional[str] = Field(default=None, description="Its main topic.")
    source_url: Optional[str] = Field(default=None, description="The request it was read from.")
    authors: List[PaperAuthorship] = Field(default_factory=list, description="Its authors.")

    @field_validator("companies", mode="before")
    def validate_companies(cls, value: JsonValue) -> JsonValue:
        """Validate the raw companies: a list, or a comma-separated text as the database aggregates them.

        Args:
            value (JsonValue): The raw companies.

        Returns:
            JsonValue: The companies, sorted, each once.
        """
        if isinstance(value, str):
            companies: List[JsonValue] = []
            companies.extend(sorted({part.strip() for part in value.split(",") if part.strip()}))
            return companies
        if value is None:
            return []
        return value

    ############################
    # Publicly Exposed Methods #
    ############################

    def link(self) -> Optional[str]:
        """Get the page to open for the paper.

        Returns:
            Optional[str]: Its DOI page, else its OpenAlex page.
        """
        if self.doi:
            return self.doi if self.doi.startswith("http") else f"https://doi.org/{self.doi}"
        return f"https://openalex.org/{self.openalex_id}"
