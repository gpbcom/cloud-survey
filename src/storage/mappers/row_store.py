from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from enum import Enum
from logging import Logger, getLogger
from typing import Dict, List, Mapping, Optional, Sequence, Union

# Third Party Imports.
from pydantic import BaseModel, JsonValue, ValidationError
from sqlalchemy import ColumnElement, RowMapping, Table, delete, insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# First Party Imports.
from storage.engine.database import Database
from storage.exception import StorageReadError, StorageWriteError

type RowValue = Optional[Union[str, int, float, bool, date, datetime]]
type RowKey = Mapping[str, RowValue]
type RowData = Dict[str, Union[JsonValue, date, datetime]]


class RowStore[Model: BaseModel]:
    """Create, read, update, delete and list the rows of one table, each row a model.

    Attributes:
        database (Database): The open database.
        table (Table): The table.
        model (type[Model]): The model of a row (its fields named as the table's columns).
        label (str): What a row is, in the logs and the errors, e.g. `company financial line`.
        keys (List[str]): The primary key columns of the table.
        logger (Logger): The store logger.

    Notes:
        - A row is the model's fields that are columns of the table (the columns the model lacks, or leaves empty,
          keep their server default, e.g. the time a row was written). A row is read back into the model from the
          columns it has.
        - A row is found by its primary key: every primary key column must be given, no other. A key the database
          generates (an identity) is left empty by `create` and read back from the inserted row.
        - `create` refuses a row whose key exists (a duplicate), `update` changes the row of the model's key and
          tells whether there was one, `delete` tells whether a row was removed.
    """

    def __init__(
        self, database: Database, table: Table, model: type[Model], label: str, logger: Optional[Logger] = None
    ) -> None:
        """Initialize the store.

        Args:
            database (Database): The open database.
            table (Table): The table.
            model (type[Model]): The model of a row.
            label (str): What a row is.
            logger (Optional[Logger]): The store logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.database = database
        self.table = table
        self.model = model
        self.label = label
        self.keys: List[str] = [column.name for column in table.primary_key.columns]
        self.logger.debug("Row store of the %s rows ready (key %s).", table.name, ", ".join(self.keys))

    ############################
    # Internal Helpers Methods #
    ############################

    def _generated(self, name: str) -> bool:
        """Tell whether the database fills a column left empty (a server default or an identity).

        Args:
            name (str): The column.

        Returns:
            bool: Whether the column has a server default or is an identity.
        """
        column = self.table.c[name]
        return column.server_default is not None or column.identity is not None

    def _row(self, value: Model, extra: Optional[RowKey] = None) -> RowData:
        """Write a model as a row: its fields that are columns, the enumerations as their values.

        Args:
            value (Model): The model.
            extra (Optional[RowKey]): The columns the model lacks, e.g. the source a repository writes beside it.

        Returns:
            RowData: The row.
        """
        dumped = value.model_dump(mode="python")
        row: RowData = {
            name: (field.value if isinstance(field, Enum) else field)
            for name, field in dumped.items()
            if name in self.table.columns and (field is not None or not self._generated(name))
        }
        row.update(extra or {})
        return row

    def _model(self, row: RowMapping) -> Model:
        """Read a row back into its model.

        Args:
            row (RowMapping): The row.

        Returns:
            Model: The model.

        Raises:
            StorageReadError: If the row does not validate as the model.
        """
        try:
            return self.model.model_validate({name: row[name] for name in self.model.model_fields if name in row})
        except ValidationError as e:
            self.logger.error("A stored %s does not validate: %s", self.label, e.errors()[0]["msg"])
            raise StorageReadError(self.label, str(e)) from e

    def _where(self, key: RowKey) -> List[ColumnElement[bool]]:
        """Build the condition of a primary key.

        Args:
            key (RowKey): The value of every primary key column.

        Returns:
            List[ColumnElement[bool]]: The equality of each key column.

        Raises:
            StorageReadError: If the key names other columns than the primary key, or misses one.
        """
        if set(key) != set(self.keys):
            self.logger.error("A %s key must name %s, not %s.", self.label, self.keys, sorted(key))
            raise StorageReadError(self.label, f"the key must name {self.keys}, not {sorted(key)}")
        return [self.table.c[name] == value for name, value in key.items()]

    def _key_of(self, row: RowData) -> RowKey:
        """Get the primary key of a row.

        Args:
            row (RowData): The row.

        Returns:
            RowKey: The value of every primary key column.

        Raises:
            StorageWriteError: If the row lacks a key column.
        """
        missing = [name for name in self.keys if name not in row]
        if missing:
            self.logger.error("A %s lacks its key columns %s.", self.label, missing)
            raise StorageWriteError(self.label, f"the key columns {missing} are missing")
        return {name: row[name] for name in self.keys}  # type: ignore[misc]

    ############################
    # Publicly Exposed Methods #
    ############################

    async def read(self, key: RowKey) -> Optional[Model]:
        """Read a row by its primary key.

        Args:
            key (RowKey): The value of every primary key column.

        Returns:
            Optional[Model]: The row, `None` when there is none.

        Raises:
            StorageReadError: If the key is malformed or the row cannot be read.
        """
        statement = select(self.table).where(*self._where(key))
        try:
            async with self.database.connect() as connection:
                row = (await connection.execute(statement)).mappings().first()
        except SQLAlchemyError as e:
            self.logger.error("The %s %s cannot be read: %s", self.label, dict(key), e)
            raise StorageReadError(self.label, str(e)) from e
        if row is None:
            self.logger.debug("No %s for %s.", self.label, dict(key))
            return None
        return self._model(row)

    async def create(self, value: Model, extra: Optional[RowKey] = None) -> Model:
        """Insert a row.

        Args:
            value (Model): The row (its generated key columns left empty).
            extra (Optional[RowKey]): The columns the model lacks.

        Returns:
            Model: The row, as stored (with its generated key).

        Raises:
            StorageWriteError: If a row has the same key (or the row breaks another constraint), or cannot be written.
        """
        row = self._row(value, extra)
        missing = [name for name in self.keys if name not in row and not self._generated(name)]
        if missing:
            self.logger.error("A %s lacks its key columns %s.", self.label, missing)
            raise StorageWriteError(self.label, f"the key columns {missing} are missing")
        statement = insert(self.table).values(row).returning(*(self.table.c[name] for name in self.keys))
        try:
            async with self.database.connect() as connection, connection.begin():
                inserted = (await connection.execute(statement)).mappings().one()
        except IntegrityError as e:
            given = {name: row.get(name) for name in self.keys}
            self.logger.error("The %s %s breaks a constraint (a duplicate key?): not created.", self.label, given)
            raise StorageWriteError(self.label, f"the row {given} breaks a constraint: {e.orig}") from e
        except SQLAlchemyError as e:
            self.logger.error("The %s cannot be created: %s", self.label, e)
            raise StorageWriteError(self.label, str(e)) from e
        key = {name: inserted[name] for name in self.keys}
        self.logger.info("%s %s created.", self.label.capitalize(), key)
        return await self.read(key) or value

    async def update(self, value: Model, extra: Optional[RowKey] = None) -> bool:
        """Replace the row of the model's key by the model.

        Args:
            value (Model): The row, its key naming the row replaced.
            extra (Optional[RowKey]): The columns the model lacks.

        Returns:
            bool: Whether a row had that key (none is created otherwise).

        Raises:
            StorageWriteError: If the row cannot be written.
        """
        row = self._row(value, extra)
        key = self._key_of(row)
        changes = {name: field for name, field in row.items() if name not in self.keys}
        statement = update(self.table).where(*self._where(key)).values(changes)
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(statement)
        except SQLAlchemyError as e:
            self.logger.error("The %s %s cannot be updated: %s", self.label, dict(key), e)
            raise StorageWriteError(self.label, str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("%s %s updated.", self.label.capitalize(), dict(key))
        else:
            self.logger.warning("No %s for %s: nothing updated.", self.label, dict(key))
        return found

    async def delete(self, key: RowKey) -> bool:
        """Delete a row by its primary key.

        Args:
            key (RowKey): The value of every primary key column.

        Returns:
            bool: Whether a row was deleted.

        Raises:
            StorageReadError: If the key is malformed.
            StorageWriteError: If the row cannot be deleted.
        """
        statement = delete(self.table).where(*self._where(key))
        try:
            async with self.database.connect() as connection, connection.begin():
                result = await connection.execute(statement)
        except SQLAlchemyError as e:
            self.logger.error("The %s %s cannot be deleted: %s", self.label, dict(key), e)
            raise StorageWriteError(self.label, str(e)) from e
        found = bool(result.rowcount)
        if found:
            self.logger.info("%s %s deleted.", self.label.capitalize(), dict(key))
        else:
            self.logger.debug("No %s for %s: nothing deleted.", self.label, dict(key))
        return found

    async def list(
        self,
        filters: Optional[Mapping[str, Sequence[RowValue]]] = None,
        offset: int = 0,
        limit: Optional[int] = None,
    ) -> List[Model]:
        """List rows, in the order of their primary key.

        Args:
            filters (Optional[Mapping[str, Sequence[RowValue]]]): For each column, the values kept (a column given
                no value keeps every row).
            offset (int): The rows skipped.
            limit (Optional[int]): The most rows returned, every one when `None`.

        Returns:
            List[Model]: The rows.

        Raises:
            StorageReadError: If a filter names an unknown column or the rows cannot be read.
        """
        statement = select(self.table).order_by(*(self.table.c[name] for name in self.keys)).offset(offset)
        for name, values in (filters or {}).items():
            if name not in self.table.columns:
                self.logger.error("The %s rows have no column %r to filter on.", self.label, name)
                raise StorageReadError(self.label, f"no column {name!r}")
            if values:
                statement = statement.where(self.table.c[name].in_(list(values)))
        if limit is not None:
            statement = statement.limit(limit)
        try:
            async with self.database.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
        except SQLAlchemyError as e:
            self.logger.error("The %s rows cannot be listed: %s", self.label, e)
            raise StorageReadError(self.label, str(e)) from e
        models = [self._model(row) for row in rows]
        self.logger.debug("%d %s rows listed.", len(models), self.label)
        return models
