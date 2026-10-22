from __future__ import annotations

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.storage.enums import DatasetKind


class UnclassifiedCount(BaseModel):
    """The listed items of a dataset nothing could categorize (filed under `other`).

    Attributes:
        provider (CloudProvider): The cloud provider.
        kind (DatasetKind): The kind of the dataset (catalogue or marketplace).
        total (int): The number of listed items.
        unclassified (int): The number of listed items filed under `other`.
    """

    model_config = ConfigDict(frozen=True)

    provider: CloudProvider = Field(description="The cloud provider.")
    kind: DatasetKind = Field(description="The kind of the dataset.")
    total: int = Field(ge=0, description="The number of listed items.")
    unclassified: int = Field(ge=0, description="The number of listed items filed under `other`.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def share(self) -> float:
        """Get the share of the unclassified items.

        Returns:
            float: The percentage of the listed items filed under `other`, 0 without item.
        """
        return self.unclassified / self.total * 100 if self.total else 0.0
