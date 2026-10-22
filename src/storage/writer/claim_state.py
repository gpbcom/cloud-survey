from __future__ import annotations

# Standard Library Imports.
from typing import NamedTuple, Optional

# First Party Imports.
from models.cloud.item_state import ItemState


class ClaimState(NamedTuple):
    """What a running crawl knows of a stored item it found (a tuple: a crawl may find millions of items).

    Attributes:
        new (bool): Whether the crawl stored the item first.
        prior (Optional[ItemState]): The item before the crawl wrote it, `None` when the crawl did not write it yet
            (the stored row is then still the item before the crawl) or when it is new.
        updated (bool): Whether the crawl dated an update of the item.
        versioned (bool): Whether the crawl wrote a version of the item.
    """

    new: bool
    prior: Optional[ItemState]
    updated: bool
    versioned: bool
