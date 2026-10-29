from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field


class AssigneeProfile(BaseModel):
    """An assignee profile of a company, derived from its stored patents.

    Attributes:
        company (str): The company.
        name (str): The assignee, as printed.
        publications (int): Its publications.
        first_year (Optional[int]): The earliest priority year.
        last_year (Optional[int]): The latest priority year.
        countries (str): The offices it filed with.
        top_cpc (Optional[str]): Its main CPC classes.
        top_inventors (Optional[str]): Its main inventors.
    """

    model_config = ConfigDict(frozen=True)

    company: str = Field(min_length=1, description="The company.")
    name: str = Field(min_length=1, description="The assignee.")
    publications: int = Field(default=0, ge=0, description="Its publications.")
    first_year: Optional[int] = Field(default=None, description="The earliest priority year.")
    last_year: Optional[int] = Field(default=None, description="The latest priority year.")
    countries: str = Field(default="", description="The offices it filed with.")
    top_cpc: Optional[str] = Field(default=None, description="Its main CPC classes.")
    top_inventors: Optional[str] = Field(default=None, description="Its main inventors.")
