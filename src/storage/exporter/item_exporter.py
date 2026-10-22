from __future__ import annotations

# Standard Library Imports.
import asyncio
import csv
import io
import json
from logging import Logger, getLogger
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, TextIO

# Third Party Imports.
from pydantic import JsonValue

# First Party Imports.
from models.cloud.categorized_item import CategorizedItem
from models.storage.enums import ExportColumn, ExportFormat
from models.storage.pages.item_query import ItemQuery
from models.storage.pages.stored_item import StoredItem
from storage.exception import StorageError, StorageExportError
from storage.repositories.item_repository import ItemRepository


class ItemExporter[T: CategorizedItem]:
    """Export the stored items matching a query to a file: CSV, a JSON array or JSON lines.

    Attributes:
        ENCODING (ClassVar[str]): The encoding of the files.
        PART_SUFFIX (ClassVar[str]): The suffix of the file being written, renamed once complete.
        IDENTITY_COLUMNS (ClassVar[List[ExportColumn]]): The storage columns written before the item fields.
        repository (ItemRepository[T]): The repository of the items.
        logger (Logger): The exporter logger.

    Notes:
        The items are streamed from the server by batches (`ItemRepository.stream`) and written as they come: an
        export of millions of items holds one batch in memory. The file is written next to its target and renamed
        once complete, so a failed export leaves no truncated file. In a CSV file, the lists and objects (categories,
        pricing, category paths) are JSON texts.
    """

    ENCODING: ClassVar[str] = "utf-8"
    PART_SUFFIX: ClassVar[str] = ".part"
    IDENTITY_COLUMNS: ClassVar[List[ExportColumn]] = [ExportColumn.ID, ExportColumn.PROVIDER]

    def __init__(self, repository: ItemRepository[T], logger: Optional[Logger] = None) -> None:
        """Initialize the exporter.

        Args:
            repository (ItemRepository[T]): The repository of the items.
            logger (Optional[Logger]): The exporter logger.
        """
        self.repository = repository
        self.logger = logger if logger else getLogger(__name__)
        self.logger.debug("Exporter of the %s items ready.", repository.kind.value)

    ############################
    # Internal Helpers Methods #
    ############################

    def _columns(self) -> List[str]:
        """Get the columns of a CSV export.

        Returns:
            List[str]: The storage identity, then the fields of the item model, its categorization last.
        """
        model = self.repository.mapper.model
        fields = [name for name in model.model_fields if name not in model.SERVICE_FIELDS]
        return [*self.IDENTITY_COLUMNS, *fields, *model.SERVICE_FIELDS]

    def _record(self, stored: StoredItem[T]) -> Dict[str, JsonValue]:
        """Get the exported record of a stored item.

        Args:
            stored (StoredItem[T]): The stored item.

        Returns:
            Dict[str, JsonValue]: Its storage identity, then its fields as JSON.
        """
        return {"id": stored.id, "provider": stored.provider.value, **stored.item.model_dump(mode="json")}

    def _cell(self, value: JsonValue) -> str:
        """Write a JSON value in a CSV cell.

        Args:
            value (JsonValue): The value.

        Returns:
            str: The text of a scalar, empty for `None`, the JSON text of a list or an object.
        """
        match value:
            case None:
                return ""
            case list() | dict():
                return json.dumps(value, ensure_ascii=False)
            case _:
                return str(value)

    def _csv_text(self, batch: List[StoredItem[T]], header: bool) -> str:
        """Write a batch of items as CSV rows.

        Args:
            batch (List[StoredItem[T]]): The items.
            header (bool): Whether the header row comes first.

        Returns:
            str: The CSV rows.
        """
        columns = self._columns()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        if header:
            writer.writerow(columns)
        for stored in batch:
            record = self._record(stored)
            writer.writerow([self._cell(record.get(column)) for column in columns])
        return buffer.getvalue()

    def _json_text(self, batch: List[StoredItem[T]], first: bool, format_: ExportFormat) -> str:
        """Write a batch of items as JSON.

        Args:
            batch (List[StoredItem[T]]): The items.
            first (bool): Whether it is the first batch of the file.
            format_ (ExportFormat): A JSON array (items separated by commas) or JSON lines.

        Returns:
            str: The JSON texts of the items.
        """
        texts = [json.dumps(self._record(stored), ensure_ascii=False) for stored in batch]
        if format_ is ExportFormat.JSON_LINES:
            return "".join(f"{text}\n" for text in texts)
        separator = "" if first else ",\n"
        return separator + ",\n".join(texts) if texts else ""

    def _text(self, batch: List[StoredItem[T]], first: bool, format_: ExportFormat) -> str:
        """Write a batch of items in a format.

        Args:
            batch (List[StoredItem[T]]): The items.
            first (bool): Whether it is the first batch of the file.
            format_ (ExportFormat): The file format.

        Returns:
            str: The text of the batch.
        """
        match format_:
            case ExportFormat.CSV:
                return self._csv_text(batch, first)
            case ExportFormat.JSON | ExportFormat.JSON_LINES:
                return self._json_text(batch, first, format_)

    async def _write_items(self, handle: TextIO, query: ItemQuery, format_: ExportFormat) -> int:
        """Write the matching items in an open file, batch by batch.

        Args:
            handle (TextIO): The open file.
            query (ItemQuery): The filters and order of the items.
            format_ (ExportFormat): The file format.

        Returns:
            int: The number of items written.

        Raises:
            StorageReadError: If the items cannot be read.
            OSError: If the file cannot be written.
        """
        written = 0
        if format_ is ExportFormat.JSON:
            await asyncio.to_thread(handle.write, "[\n")
        async for batch in self.repository.stream(query):
            await asyncio.to_thread(handle.write, self._text(batch, written == 0, format_))
            written += len(batch)
            self.logger.debug("%d %s items exported.", written, self.repository.kind.value)
        if format_ is ExportFormat.JSON:
            await asyncio.to_thread(handle.write, "\n]\n")
        elif format_ is ExportFormat.CSV and written == 0:
            await asyncio.to_thread(handle.write, self._csv_text([], True))
        return written

    ############################
    # Publicly Exposed Methods #
    ############################

    async def export(self, query: ItemQuery, path: Path, format_: ExportFormat) -> int:
        """Export the items matching a query to a file, in the order of the query.

        Args:
            query (ItemQuery): The filters and order of the items (its bounds are ignored).
            path (Path): The file, replaced if it exists.
            format_ (ExportFormat): The file format.

        Returns:
            int: The number of items exported.

        Raises:
            StorageExportError: If the file cannot be written.
            StorageError: If the items cannot be read.
        """
        part = path.with_name(path.name + self.PART_SUFFIX)
        self.logger.info("Exporting the matching %s items to %s (%s).", self.repository.kind.value, path, format_.value)
        try:
            with part.open("w", encoding=self.ENCODING, newline="") as handle:
                written = await self._write_items(handle, query, format_)
            part.replace(path)
        except OSError as e:
            part.unlink(missing_ok=True)
            self.logger.error("The %s items cannot be exported to %s: %s", self.repository.kind.value, path, e)
            raise StorageExportError(str(path), e.strerror or str(e)) from e
        except StorageError:
            part.unlink(missing_ok=True)
            self.logger.error("The %s items cannot be read for %s.", self.repository.kind.value, path)
            raise
        self.logger.info("%d %s items exported to %s.", written, self.repository.kind.value, path)
        return written
