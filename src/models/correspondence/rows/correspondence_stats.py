from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field


class CorrespondenceStats(BaseModel):
    """The figures of the correspondences of the chosen provider columns.

    Attributes:
        concepts (int): The concepts shown.
        matched (int): The services of the columns filed under a concept shared with another column.
        services (int): The listed services of the columns.
        pending (int): The services of the columns the language model has not matched yet.
        last_checked (Optional[datetime]): When the language model last matched services, `None` before any match.
        stored (int): The concepts stored, whatever the columns and the filters (none before the first AI match).
    """

    model_config = ConfigDict(frozen=True)

    concepts: int = Field(default=0, ge=0, description="The concepts shown.")
    matched: int = Field(default=0, ge=0, description="The services with an equivalent in another column.")
    services: int = Field(default=0, ge=0, description="The listed services of the columns.")
    pending: int = Field(default=0, ge=0, description="The services not matched yet.")
    last_checked: Optional[datetime] = Field(default=None, description="When services were last matched.")
    stored: int = Field(default=0, ge=0, description="The concepts stored.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def coverage(self) -> float:
        """Get the share of the services with an equivalent in another column.

        Returns:
            float: The share, in percent (0 without service).
        """
        return 100 * self.matched / self.services if self.services else 0.0
