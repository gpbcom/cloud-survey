from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import AwareDatetime, BaseModel, Field

# First Party Imports.
from models.storage.enums import DatasetKind


class DatasetStamp(BaseModel):
    """The state of a stored dataset, cheap to read: its readers reload it when its revision changes.

    Attributes:
        kind (DatasetKind): What the dataset holds.
        dataset (str): The cloud provider, or the statistics source.
        label (Optional[str]): A readable name of the dataset source, when it has one (e.g. `Synergy Research Group`).
        crawled_at (AwareDatetime): When the last crawl of the dataset started.
        in_progress (bool): Whether a crawl is still writing the dataset.
        size (int): The number of items still listed by the website.
        revision (int): A number growing at each write of the dataset.
    """

    kind: DatasetKind = Field(description="What the dataset holds.")
    dataset: str = Field(min_length=1, max_length=100, description="The cloud provider, or the statistics source.")
    label: Optional[str] = Field(default=None, max_length=200, description="A readable name of the dataset source.")
    crawled_at: AwareDatetime = Field(description="When the last crawl of the dataset started.")
    in_progress: bool = Field(default=False, description="Whether a crawl is still writing the dataset.")
    size: int = Field(default=0, ge=0, description="The number of items still listed by the website.")
    revision: int = Field(default=0, ge=0, description="A number growing at each write of the dataset.")
