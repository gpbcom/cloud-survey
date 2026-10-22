from __future__ import annotations

# Standard Library Imports.
from typing import Protocol, runtime_checkable

# First Party Imports.
from models.cloud.enums import CloudProvider


@runtime_checkable
class IdentifiedRow(Protocol):
    """A row of a paged table, holding a stored item with its storage identity.

    Attributes:
        id (int): The storage identifier of the item.
        provider (CloudProvider): The cloud provider of the item.
    """

    ############################
    # Publicly Exposed Methods #
    ############################

    @property
    def id(self) -> int:
        """Get the storage identifier of the item.

        Returns:
            int: The identifier.
        """

    @property
    def provider(self) -> CloudProvider:
        """Get the cloud provider of the item.

        Returns:
            CloudProvider: The cloud provider.
        """
