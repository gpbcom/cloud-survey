from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider


class CoverageCell(BaseModel):
    """How many services of a provider have an equivalent at another provider.

    Attributes:
        source (CloudProvider): The provider whose services are counted.
        target (CloudProvider): The provider where an equivalent is looked for.
        matched (int): The listed services of the source sharing a concept with a service of the target.
        total (int): The listed services of the source.
    """

    model_config = ConfigDict(frozen=True)

    source: CloudProvider = Field(description="The provider whose services are counted.")
    target: CloudProvider = Field(description="The provider where an equivalent is looked for.")
    matched: int = Field(default=0, ge=0, description="The services with an equivalent at the target.")
    total: int = Field(default=0, ge=0, description="The listed services of the source.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def share(self) -> float:
        """Get the share of the services of the source having an equivalent at the target.

        Returns:
            float: The share, in percent (0 without service).
        """
        return 100 * self.matched / self.total if self.total else 0.0
