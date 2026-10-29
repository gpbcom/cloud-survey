from __future__ import annotations

# Third Party Imports.
from sqlalchemy import BigInteger, Identity, Index, String
from sqlalchemy.orm import Mapped, mapped_column

# First Party Imports.
from models.storage.enums import StorageTable
from storage.tables.base import Base
from storage.tables.prices.staging.price_columns import PriceColumns


class ServicePriceStageRow(PriceColumns, Base):
    """A price a running price crawl read, waiting to be merged into the stored prices (an unlogged table).

    Attributes:
        id (Mapped[int]): The row identifier.
        run_id (Mapped[str]): The price crawl of a provider which read it: its rows are merged together at its end,
            then removed.

    Notes:
        The crawl copies its batches here (`COPY`, without write-ahead log), so that one set-based merge compares
        them with the stored prices: the memory of the crawl never holds a whole price list.
    """

    __tablename__ = StorageTable.SERVICE_PRICE_STAGE
    __table_args__ = (
        Index("ix_service_price_stage_run_sku", "run_id", "sku_key"),
        {"prefixes": ["UNLOGGED"]},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40))
