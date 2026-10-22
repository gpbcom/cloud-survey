from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import AwareDatetime, BaseModel, Field

# First Party Imports.
from models.storage.enums import CrawlStatus, DatasetKind


class CrawlSummary(BaseModel):
    """What a crawl wrote to the storage.

    Attributes:
        crawl_id (int): The identifier of the stored crawl.
        kind (DatasetKind): What was crawled.
        dataset (str): The crawled dataset: the cloud provider, or the statistics source.
        status (CrawlStatus): The outcome of the crawl.
        started_at (AwareDatetime): When the crawl started: the date of its additions, updates and deletions.
        finished_at (Optional[AwareDatetime]): When the crawl was over, `None` while it runs.
        found (int): The number of distinct items crawled.
        added (int): The number of items new since the previous crawl.
        updated (int): The number of items updated since the previous crawl.
        deleted (int): The number of items missing from the crawl, marked deleted.
        size (int): The number of items still listed by the website after the crawl.
    """

    crawl_id: int = Field(ge=1, description="The identifier of the stored crawl.")
    kind: DatasetKind = Field(description="What was crawled.")
    dataset: str = Field(min_length=1, max_length=100, description="The cloud provider, or the statistics source.")
    status: CrawlStatus = Field(description="The outcome of the crawl.")
    started_at: AwareDatetime = Field(description="When the crawl started.")
    finished_at: Optional[AwareDatetime] = Field(default=None, description="When the crawl was over.")
    found: int = Field(default=0, ge=0, description="The number of distinct items crawled.")
    added: int = Field(default=0, ge=0, description="The number of items new since the previous crawl.")
    updated: int = Field(default=0, ge=0, description="The number of items updated since the previous crawl.")
    deleted: int = Field(default=0, ge=0, description="The number of items marked deleted.")
    size: int = Field(default=0, ge=0, description="The number of items still listed after the crawl.")
