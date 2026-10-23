from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
from sqlalchemy import Table, func, select
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.markets.enums import MarketFeed
from models.markets.facts.price_point import PricePoint
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.tables.base import Base
from storage.tables.markets.stock_price_row import StockPriceRow


class StockPriceRepository:
    """Read and write the closing prices of the listings.

    Attributes:
        CHUNK (int): The rows written per statement.
        database (Database): The open database.
        table (Table): The `stock_prices` table.
        logger (Logger): The repository logger.

    Notes:
        A price is identified by its listing, day and source: a crawl rewrites the days it read (the last week
        moves until it closes), the older ones are kept, so a listing Google stops answering keeps its history.
    """

    CHUNK = 2000

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.table: Table = Base.metadata.tables[StockPriceRow.__tablename__]
        self.logger.debug("Repository of the stock prices ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def upsert(self, points: Sequence[PricePoint], source: MarketFeed = MarketFeed.GOOGLE_FINANCE) -> int:
        """Write prices, replacing those of the same listing, day and source.

        Args:
            points (Sequence[PricePoint]): The prices.
            source (MarketFeed): Where they come from.

        Returns:
            int: The number of prices written.

        Raises:
            StorageWriteError: If the prices cannot be written.
        """
        unique: Dict[Tuple[str, date], PricePoint] = {(point.listing, point.day): point for point in points}
        rows = [
            {
                "listing": point.listing,
                "day": point.day,
                "source": source.value,
                "close": point.close,
                "volume": point.volume,
                "currency": point.currency,
                "source_url": point.source_url,
            }
            for point in unique.values()
        ]
        if not rows:
            return 0
        table = self.table
        try:
            async with self.database.connect() as connection, connection.begin():
                for start in range(0, len(rows), self.CHUNK):
                    statement = upsert(table).values(rows[start : start + self.CHUNK])
                    await connection.execute(
                        statement.on_conflict_do_update(
                            index_elements=[table.c.listing, table.c.day, table.c.source],
                            set_={
                                "close": statement.excluded.close,
                                "volume": statement.excluded.volume,
                                "currency": statement.excluded.currency,
                                "source_url": statement.excluded.source_url,
                                "fetched_at": func.now(),
                            },
                        )
                    )
        except SQLAlchemyError as e:
            self.logger.error("The stock prices cannot be written: %s", e)
            raise StorageWriteError("stock prices", str(e)) from e
        self.logger.info("%d stock prices written.", len(rows))
        return len(rows)

    async def read(
        self, listings: Optional[Sequence[str]] = None, start: Optional[date] = None, end: Optional[date] = None
    ) -> List[PricePoint]:
        """Read prices.

        Args:
            listings (Optional[Sequence[str]]): Only these listings, every one when `None` or empty.
            start (Optional[date]): Only from this day.
            end (Optional[date]): Only up to this day.

        Returns:
            List[PricePoint]: The prices, by listing then day.

        Raises:
            StorageReadError: If the prices cannot be read.
        """
        table = self.table
        statement = select(table).order_by(table.c.listing, table.c.day)
        if listings:
            statement = statement.where(table.c.listing.in_(list(listings)))
        if start is not None:
            statement = statement.where(table.c.day >= start)
        if end is not None:
            statement = statement.where(table.c.day <= end)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The stock prices cannot be read: %s", e)
            raise StorageReadError("stock prices", str(e)) from e
        points = [
            PricePoint(
                listing=row["listing"],
                day=row["day"],
                close=row["close"],
                volume=row["volume"],
                currency=row["currency"],
                source_url=row["source_url"] or row["source"],
            )
            for row in rows
        ]
        self.logger.debug("%d stock prices read.", len(points))
        return points

    async def spans(self) -> Dict[str, Tuple[date, date, int]]:
        """Get the stored span of every listing.

        Returns:
            Dict[str, Tuple[date, date, int]]: The first day, the last day and the number of prices, by listing.

        Raises:
            StorageReadError: If the prices cannot be read.
        """
        table = self.table
        statement = select(table.c.listing, func.min(table.c.day), func.max(table.c.day), func.count()).group_by(
            table.c.listing
        )
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).all()
        except SQLAlchemyError as e:
            self.logger.error("The stock price spans cannot be read: %s", e)
            raise StorageReadError("stock prices", str(e)) from e
        spans = {str(row[0]): (row[1], row[2], int(row[3])) for row in rows}
        self.logger.debug("Stock prices stored for %d listings.", len(spans))
        return spans
