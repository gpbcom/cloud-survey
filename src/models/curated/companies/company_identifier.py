from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.curated.enums import IdentifierKind, IdentifierStatus, RecordOrigin


class CompanyIdentifier(BaseModel):
    """An identifier of a company at a source: a SEC filer, an OpenAlex institution, a Google Patents assignee.

    Attributes:
        company (str): The company key.
        kind (IdentifierKind): What it identifies the company at.
        value (str): The identifier (a CIK, an institution, an assignee name, a pattern).
        position (int): Its rank among the company's identifiers of its kind.
        status (IdentifierStatus): Whether it is used (confirmed), proposed (candidate) or refused.
        origin (RecordOrigin): Where it comes from.
        evidence_url (Optional[str]): The page that shows it (a resolver's).
        note (Optional[str]): What the research noted about it.
        checked_at (Optional[datetime]): When a resolver checked it last.
        edited (bool): Whether a person changed it.
    """

    model_config = ConfigDict(frozen=True)

    company: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=40, description="The company key.")
    kind: IdentifierKind = Field(description="What it identifies the company at.")
    value: str = Field(min_length=1, max_length=300, description="The identifier.")
    position: int = Field(ge=0, description="Its rank among the identifiers of its kind.")
    status: IdentifierStatus = Field(default=IdentifierStatus.CONFIRMED, description="Whether it is used.")
    origin: RecordOrigin = Field(default=RecordOrigin.SEED, description="Where it comes from.")
    evidence_url: Optional[str] = Field(default=None, max_length=2048, description="The page that shows it.")
    note: Optional[str] = Field(default=None, description="What the research noted about it.")
    checked_at: Optional[datetime] = Field(default=None, description="When a resolver checked it last.")
    edited: bool = Field(default=False, description="Whether a person changed it.")
