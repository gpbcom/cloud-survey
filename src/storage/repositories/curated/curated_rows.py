from __future__ import annotations

# Standard Library Imports.
from datetime import datetime
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union, cast

# Third Party Imports.
from pydantic import BaseModel, JsonValue
from sqlalchemy import ColumnElement, Table, func, select
from sqlalchemy.dialects.postgresql import insert as upsert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

# First Party Imports.
from models.curated.enums import CuratedFile
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError
from storage.mappers.row_store import RowKey, RowStore, RowValue
from storage.repositories.curated.curated_state_repository import CuratedStateRepository

type CuratedValue = Union[JsonValue, datetime]
type CuratedColumn = Union[str, int, bool, datetime, JsonValue]


class CuratedRows[Model: BaseModel]:
    """Create, read, update, delete, list and upsert the rows of one curated table, each row a model.

    Attributes:
        CHUNK (ClassVar[int]): The rows written per statement.
        database (Database): The open database.
        table (Table): The table.
        model (type[Model]): The model of a row.
        label (str): What a row is, in the logs and the errors.
        files (Dict[str, CuratedFile]): The bundle file of a row, by the prefix of the value of its `file_column`
            (the only file under `""` when `file_column` is `None`).
        file_column (Optional[str]): The column naming the bundle file of a row (the records of two files).
        order (List[str]): The columns the rows are listed by (their position last).
        state (CuratedStateRepository): The revisions of the bundle files, incremented by every write.
        rows (RowStore[Model]): The single-row operations.
        logger (Logger): The rows logger.

    Notes:
        - A row a person changed (`edited`) is never overwritten by an upsert (a reseed), unless asked.
        - Every write increments the revision of the bundle file of its rows, so that the catalogues read from the
          database are read again.
    """

    CHUNK: ClassVar[int] = 1000

    def __init__(
        self,
        database: Database,
        table: Table,
        model: type[Model],
        label: str,
        files: Dict[str, CuratedFile],
        order: Sequence[str],
        state: CuratedStateRepository,
        file_column: Optional[str] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the rows.

        Args:
            database (Database): The open database.
            table (Table): The table.
            model (type[Model]): The model of a row.
            label (str): What a row is.
            files (Dict[str, CuratedFile]): The bundle file of a row, by the value of its `file_column` (the only
                file under the key `""` when `file_column` is `None`).
            order (Sequence[str]): The columns the rows are listed by.
            state (CuratedStateRepository): The revisions of the bundle files.
            file_column (Optional[str]): The column naming the bundle file of a row.
            logger (Optional[Logger]): The rows logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.table = table
        self.model = model
        self.label = label
        self.files = dict(files)
        self.file_column = file_column
        self.order = list(order)
        self.state = state
        self.rows = RowStore(database, table, model, label, self.logger)
        self.logger.debug("Curated rows of %s ready.", table.name)

    ############################
    # Internal Helpers Methods #
    ############################

    def _file_of(self, raw: Optional[RowValue]) -> CuratedFile:
        """Get the bundle file of a row from the value of its file column.

        Args:
            raw (Optional[RowValue]): The value of the row's `file_column`, `None` for a table of one file.

        Returns:
            CuratedFile: Its bundle file.
        """
        if self.file_column is None or raw is None:
            return self.files[""]
        text = str(raw)
        return next(file for prefix, file in self.files.items() if prefix and text.startswith(prefix))

    async def _bump(self, raws: Sequence[Optional[RowValue]]) -> None:
        """Increment the revision of the bundle files of some rows.

        Args:
            raws (Sequence[Optional[RowValue]]): The values of the file column of the rows written.

        Raises:
            StorageWriteError: If a revision cannot be written.
        """
        files: Set[CuratedFile] = {self._file_of(raw) for raw in raws}
        for file in sorted(files):
            await self.state.bump(file)

    def _raw(self, value: Model) -> Optional[RowValue]:
        """Get the value of the file column of a row.

        Args:
            value (Model): The row.

        Returns:
            Optional[RowValue]: The value, `None` for a table of one file.
        """
        if self.file_column is None:
            return None
        raw = value.model_dump()[self.file_column]
        return str(raw) if raw is not None else None

    def _row(self, value: Model) -> Dict[str, CuratedValue]:
        """Write a model as a row of the table (its fields that are columns).

        Args:
            value (Model): The model.

        Returns:
            Dict[str, CuratedValue]: The row.
        """
        dumped = value.model_dump()
        return {name: item for name, item in dumped.items() if name in self.table.columns}

    async def _write(self, connection: AsyncConnection, values: Sequence[Model], replace_edited: bool) -> int:
        """Upsert rows on a connection, the rows a person changed kept unless asked.

        Args:
            connection (AsyncConnection): The connection, in a transaction.
            values (Sequence[Model]): The rows.
            replace_edited (bool): Whether the rows a person changed are replaced too.

        Returns:
            int: The rows written.
        """
        keys = [column.name for column in self.table.primary_key.columns]
        rows = [self._row(value) for value in values]
        written = 0
        for start in range(0, len(rows), self.CHUNK):
            inserted = upsert(self.table).values(rows[start : start + self.CHUNK])
            excluded = inserted.excluded
            updated: Dict[str, ColumnElement[CuratedColumn]] = {
                name: excluded[name] for name in rows[0] if name not in keys and name != "updated_at"
            }
            updated["updated_at"] = cast(ColumnElement[CuratedColumn], func.now())
            statement = inserted.on_conflict_do_update(
                index_elements=[self.table.c[name] for name in keys],
                set_=updated,
                where=None if replace_edited else ~self.table.c.edited,
            ).returning(self.table.c[keys[0]])
            written += len((await connection.execute(statement)).all())
        return written

    ############################
    # Publicly Exposed Methods #
    ############################

    async def create(self, value: Model) -> Model:
        """Insert a row.

        Args:
            value (Model): The row.

        Returns:
            Model: The row, as stored.

        Raises:
            StorageWriteError: If the row exists or cannot be written.
        """
        created = await self.rows.create(value)
        await self._bump([self._raw(value)])
        return created

    async def read(self, key: RowKey) -> Optional[Model]:
        """Read a row.

        Args:
            key (RowKey): Its primary key.

        Returns:
            Optional[Model]: The row, `None` when there is none.

        Raises:
            StorageReadError: If the row cannot be read.
        """
        return await self.rows.read(key)

    async def update(self, value: Model) -> bool:
        """Replace a row (that of the same primary key).

        Args:
            value (Model): The row.

        Returns:
            bool: Whether the row existed (none is created otherwise).

        Raises:
            StorageWriteError: If the row cannot be written.
        """
        found = await self.rows.update(value)
        if found:
            await self._bump([self._raw(value)])
        return found

    async def delete(self, key: RowKey) -> bool:
        """Remove a row.

        Args:
            key (RowKey): Its primary key.

        Returns:
            bool: Whether there was a row.

        Raises:
            StorageWriteError: If the row cannot be removed.
        """
        found = await self.rows.delete(key)
        if found:
            await self._bump([key.get(self.file_column) if self.file_column else None])
        return found

    async def list(self, filters: Optional[Mapping[str, Sequence[RowValue]]] = None) -> List[Model]:
        """List the rows in their order.

        Args:
            filters (Optional[Mapping[str, Sequence[RowValue]]]): For each column, the values kept.

        Returns:
            List[Model]: The rows, by the order columns.

        Raises:
            StorageReadError: If a filter names an unknown column or the rows cannot be read.
        """
        statement = select(self.table).order_by(*(self.table.c[name] for name in self.order))
        for name, values in (filters or {}).items():
            if name not in self.table.columns:
                self.logger.error("The %s rows have no column %r to filter on.", self.label, name)
                raise StorageReadError(self.label, f"no column {name!r}")
            if values:
                statement = statement.where(self.table.c[name].in_(list(values)))
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The %s rows cannot be listed: %s", self.label, e)
            raise StorageReadError(self.label, str(e)) from e
        fields = self.model.model_fields
        models = [self.model.model_validate({name: row[name] for name in fields if name in row}) for row in rows]
        self.logger.debug("%d %s rows listed.", len(models), self.label)
        return models

    async def upsert(
        self, values: Sequence[Model], replace_edited: bool = False, connection: Optional[AsyncConnection] = None
    ) -> Tuple[int, int]:
        """Write rows, replacing those of the same key, the rows a person changed kept unless asked.

        Args:
            values (Sequence[Model]): The rows.
            replace_edited (bool): Whether the rows a person changed are replaced too.
            connection (Optional[AsyncConnection]): A connection in a transaction to write on (a seed), whose
                caller records the revision. A connection of the pool otherwise, the revision incremented here.

        Returns:
            Tuple[int, int]: The rows written, then the rows kept because a person changed them.

        Raises:
            StorageWriteError: If the rows cannot be written.
        """
        if not values:
            return 0, 0
        try:
            if connection is not None:
                written = await self._write(connection, values, replace_edited)
            else:
                async with self.database.connect() as own, own.begin():
                    written = await self._write(own, values, replace_edited)
        except SQLAlchemyError as e:
            self.logger.error("The %s rows cannot be written: %s", self.label, e)
            raise StorageWriteError(self.label, str(e)) from e
        if connection is None:
            await self._bump([self._raw(value) for value in values])
        kept = len(values) - written
        if kept:
            self.logger.warning("%d %s rows changed by a person were kept.", kept, self.label)
        self.logger.info("%d %s rows written.", written, self.label)
        return written, kept
