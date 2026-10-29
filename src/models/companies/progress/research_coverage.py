from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field


class ResearchCoverage(BaseModel):
    """What the database holds of a company's patents and papers.

    Attributes:
        company (str): The company.
        patents (int): The publications its assignee searches found.
        pages (int): Those whose page (citations, family, classes) was read.
        windows_done (int): The patents search windows complete.
        windows_open (int): The windows still to search (pending or incomplete): the next runs resume them.
        papers (int): The research papers of its institutions.
        researchers (int): The profiles of its researchers.
    """

    model_config = ConfigDict(frozen=True)

    company: str = Field(min_length=1, description="The company.")
    patents: int = Field(default=0, ge=0, description="The publications found.")
    pages: int = Field(default=0, ge=0, description="The publications whose page was read.")
    windows_done: int = Field(default=0, ge=0, description="The search windows complete.")
    windows_open: int = Field(default=0, ge=0, description="The search windows still open.")
    papers: int = Field(default=0, ge=0, description="The research papers.")
    researchers: int = Field(default=0, ge=0, description="The researcher profiles.")
