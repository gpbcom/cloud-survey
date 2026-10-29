from __future__ import annotations

# Standard Library Imports.
from typing import List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.companies.patents.patent_citation import PatentCitation
from models.companies.stored.patents.stored_patent import StoredPatent


class PatentFile(BaseModel):
    """Everything stored about one patent publication: the detail pane of the Patents & Papers tab.

    Attributes:
        patent (StoredPatent): The publication.
        abstract (Optional[str]): Its abstract (from its page).
        inventors (List[str]): Its inventors, in order.
        assignees_original (List[str]): The assignees it was filed by.
        assignees_current (List[str]): The assignees holding it now.
        cpc (List[str]): Its CPC classes, the main one first.
        citations (List[PatentCitation]): The publications it cites and those citing it.
    """

    model_config = ConfigDict(frozen=True)

    patent: StoredPatent = Field(description="The publication.")
    abstract: Optional[str] = Field(default=None, description="Its abstract.")
    inventors: List[str] = Field(default_factory=list, description="Its inventors.")
    assignees_original: List[str] = Field(default_factory=list, description="The assignees it was filed by.")
    assignees_current: List[str] = Field(default_factory=list, description="The assignees holding it now.")
    cpc: List[str] = Field(default_factory=list, description="Its CPC classes, the main one first.")
    citations: List[PatentCitation] = Field(default_factory=list, description="Its citations.")
