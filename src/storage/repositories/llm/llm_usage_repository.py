from __future__ import annotations

# Standard Library Imports.
from decimal import Decimal
from logging import Logger, getLogger
from typing import List, Optional, Tuple

# Third Party Imports.
from sqlalchemy import Table, func, insert, select
from sqlalchemy.exc import SQLAlchemyError

# First Party Imports.
from models.storage.usage.llm_call import LlmCall
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.row_store import RowStore
from storage.tables.base import Base
from storage.tables.llm.llm_usage_row import LlmUsageRow


class LlmUsageRepository:
    """Record the language model calls and what they cost, for the budget and the Categories manager.

    Attributes:
        database (Database): The open database.
        table (Table): The `llm_usage` table.
        rows (RowStore[LlmCall]): The single-call operations on the table.
        logger (Logger): The repository logger.
    """

    def __init__(self, database: Database, logger: Optional[Logger] = None) -> None:
        """Initialize the repository.

        Args:
            database (Database): The open database.
            logger (Optional[Logger]): The repository logger.
        """
        self.database = database
        self.logger = logger if logger else getLogger(__name__)
        self.table: Table = Base.metadata.tables[LlmUsageRow.__tablename__]
        self.rows = RowStore(database, self.table, LlmCall, "language model call", self.logger)
        self.logger.debug("Repository of the language model usage ready.")

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, call: LlmCall) -> LlmCall:
        """Insert one call.

        Args:
            call (LlmCall): The call (its identifier and time left empty: the database gives them).

        Returns:
            LlmCall: The call, as stored.

        Raises:
            StorageWriteError: If the call cannot be written.
        """
        self.logger.debug("Creating a %s call to %s.", call.task, call.model)
        return await self.rows.create(call)

    async def read(self, call_id: int) -> Optional[LlmCall]:
        """Read one call.

        Args:
            call_id (int): The identifier of the call.

        Returns:
            Optional[LlmCall]: The call, `None` when there is none.

        Raises:
            StorageReadError: If the call cannot be read.
        """
        return await self.rows.read({"id": call_id})

    async def update(self, call: LlmCall) -> bool:
        """Replace one call (that of the same identifier).

        Args:
            call (LlmCall): The call.

        Returns:
            bool: Whether the call existed (none is created otherwise).

        Raises:
            StorageWriteError: If the call has no identifier, or cannot be written.
        """
        if call.id is None:
            self.logger.error("A %s call to %s without identifier cannot be updated.", call.task, call.model)
            raise StorageWriteError("language model usage", "the call to update has no identifier")
        return await self.rows.update(call)

    async def delete(self, call_id: int) -> bool:
        """Delete one call.

        Args:
            call_id (int): The identifier of the call.

        Returns:
            bool: Whether a call was deleted.

        Raises:
            StorageWriteError: If the call cannot be deleted.
        """
        return await self.rows.delete({"id": call_id})

    async def list(
        self, tasks: Optional[List[str]] = None, offset: int = 0, limit: Optional[int] = None
    ) -> List[LlmCall]:
        """List calls, the oldest first.

        Args:
            tasks (Optional[List[str]]): Only these tasks, every one when `None` or empty.
            offset (int): The calls skipped.
            limit (Optional[int]): The most calls returned, every one when `None`.

        Returns:
            List[LlmCall]: The calls.

        Raises:
            StorageReadError: If the calls cannot be read.
        """
        return await self.rows.list({"task": tasks or []}, offset, limit)

    async def record(
        self,
        task: str,
        provider: str,
        model: str,
        tokens: Tuple[int, int, int, int],
        cost: Decimal,
        currency: str,
    ) -> None:
        """Record a call.

        Args:
            task (str): The task of the call.
            provider (str): The provider of the model.
            model (str): The model.
            tokens (Tuple[int, int, int, int]): The uncached input, output, cache read and cache write tokens.
            cost (Decimal): The cost of the call.
            currency (str): Its currency.

        Raises:
            StorageWriteError: If the call cannot be recorded.
        """
        uncached, output, cache_read, cache_write = tokens
        try:
            async with self.database.connect() as connection, connection.begin():
                await connection.execute(
                    insert(self.table).values(
                        task=task,
                        provider=provider,
                        model=model,
                        input_tokens=uncached,
                        output_tokens=output,
                        cache_read_tokens=cache_read,
                        cache_write_tokens=cache_write,
                        cost=cost,
                        currency=currency,
                    )
                )
        except SQLAlchemyError as e:
            self.logger.error("The %s call to %s cannot be recorded: %s", task, model, e)
            raise StorageWriteError("language model usage", str(e)) from e
        self.logger.info("%s call to %s recorded: %.6f %s.", task, model, cost, currency)

    async def spent(self, currency: str) -> Decimal:
        """Sum what the recorded calls cost.

        Args:
            currency (str): The currency summed (the calls of another currency are left out).

        Returns:
            Decimal: The total cost.

        Raises:
            StorageReadError: If the calls cannot be read.
        """
        try:
            async with self.database.connect() as connection:
                total = await connection.scalar(
                    select(func.coalesce(func.sum(self.table.c.cost), 0)).where(self.table.c.currency == currency)
                )
        except SQLAlchemyError as e:
            self.logger.error("The language model spending cannot be read: %s", e)
            raise StorageReadError("language model usage", str(e)) from e
        spent = Decimal(str(total or 0))
        self.logger.debug("Language model calls spent %.4f %s.", spent, currency)
        return spent
