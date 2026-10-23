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
from models.markets.values.fx_rate import FxRate
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.tables.base import Base
from storage.tables.markets.fx_rate_row import FxRateRow


class FxRateRepository:
    """Read and write the exchange rates against the US dollar.

    Attributes:
        CHUNK (int): The rows written per statement.
        database (Database): The open database.
        table (Table): The `fx_rates` table.
        logger (Logger): The repository logger.
    """

    CHUNK = 5000

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.table: Table = Base.metadata.tables[FxRateRow.__tablename__]
        self.logger.debug("Repository of the exchange rates ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def upsert(self, rates: Sequence[FxRate]) -> int:
        """Write rates, replacing those of the same currency and day.

        Args:
            rates (Sequence[FxRate]): The rates.

        Returns:
            int: The number of rates written.

        Raises:
            StorageWriteError: If the rates cannot be written.
        """
        unique: Dict[Tuple[str, date], FxRate] = {(rate.currency, rate.day): rate for rate in rates}
        rows = [
            {"currency": rate.currency, "day": rate.day, "usd_per_unit": rate.usd_per_unit, "source": rate.source.value}
            for rate in unique.values()
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
                            index_elements=[table.c.currency, table.c.day],
                            set_={
                                "usd_per_unit": statement.excluded.usd_per_unit,
                                "source": statement.excluded.source,
                                "fetched_at": func.now(),
                            },
                        )
                    )
        except SQLAlchemyError as e:
            self.logger.error("The exchange rates cannot be written: %s", e)
            raise StorageWriteError("exchange rates", str(e)) from e
        self.logger.info("%d exchange rates written.", len(rows))
        return len(rows)

    async def read(self, currencies: Optional[Sequence[str]] = None) -> List[FxRate]:
        """Read rates.

        Args:
            currencies (Optional[Sequence[str]]): Only these currencies, every one when `None` or empty.

        Returns:
            List[FxRate]: The rates, by currency then day.

        Raises:
            StorageReadError: If the rates cannot be read.
        """
        table = self.table
        statement = select(table).order_by(table.c.currency, table.c.day)
        if currencies:
            statement = statement.where(table.c.currency.in_(list(currencies)))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The exchange rates cannot be read: %s", e)
            raise StorageReadError("exchange rates", str(e)) from e
        rates = [
            FxRate(currency=row["currency"], day=row["day"], usd_per_unit=row["usd_per_unit"], source=row["source"])
            for row in rows
        ]
        self.logger.debug("%d exchange rates read.", len(rates))
        return rates
