from __future__ import annotations

# Third Party Imports.
from sqlalchemy import BigInteger, Identity, Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base
from storage.tables.prices.staging.free_tier_columns import FreeTierColumns


class FreeTierStageRow(FreeTierColumns, Base):
    """A free offer a running price crawl read, waiting to be merged into the stored offers (an unlogged table).

    Attributes:
        id (Mapped[int]): The row identifier.
        run_id (Mapped[str]): The price crawl of a provider which read it.
    """

    __tablename__ = StorageTable.FREE_TIER_STAGE
    __table_args__ = (
        Index("ix_free_tier_stage_run_key", "run_id", "free_key"),
        {"prefixes": ["UNLOGGED"]},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40))
