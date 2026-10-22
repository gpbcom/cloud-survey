from __future__ import annotations

# Standard Library Imports.
from typing import Dict

# Third Party Imports.
from pydantic import BaseModel, Field

# First Party Imports.
from models.cloud.dated_item import DatedItem
from models.storage.dataset_stamp import DatasetStamp


class DatasetChanges[T: DatedItem](BaseModel):
    """The items of a stored dataset written since a given revision, to refresh a copy of it.

    Attributes:
        stamp (DatasetStamp): The state of the dataset when the changes were read.
        items (Dict[int, T]): The items written since the given revision, by storage identifier. Items are never
            removed from the storage (the deleted ones keep their deletion date): the changes replace or extend the
            items of the copy.
        revision (int): The revision to read the next changes from.
    """

    stamp: DatasetStamp = Field(description="The state of the dataset when the changes were read.")
    items: Dict[int, T] = Field(default_factory=dict, description="The items written since the revision, by id.")
    revision: int = Field(ge=0, description="The revision to read the next changes from.")
