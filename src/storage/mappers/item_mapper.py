from __future__ import annotations

# Standard Library Imports.
from datetime import date, datetime
from enum import Enum
from hashlib import blake2b
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple, Type, Union

# Third Party Imports.
from pydantic import JsonValue
from sqlalchemy import Column, Table
from sqlalchemy.engine import RowMapping

# First Party Imports.
from models.cloud.categorized_item import CategorizedItem
from models.cloud.dated_item import DATE_FIELDS
from models.cloud.item_state import ItemState

type RowValue = Union[JsonValue, bytes, datetime, date]


class ItemMapper[T: CategorizedItem]:
    """Convert the crawled items (products or software) to the rows of their table, and back.

    Attributes:
        HASH_SIZE (ClassVar[int]): The size of the match key hashes, in bytes.
        model (Type[T]): The item model.
        table (Table): The items table, whose columns are named after the model fields.
        versions (Table): The versions table of the items.
        fields (List[str]): The model fields, each stored in the column of the same name.
        content_fields (List[str]): The model fields stored in the versions: without the dates and the
            categorization (see `CategorizedItem.SERVICE_FIELDS`).
        logger (Logger): The mapper logger.

    Notes:
        The match keys of an item (its page, then its name) are
        stored as fixed-size BLAKE2b hashes: the indexes stay
        small whatever the length of the pages and names.
    """

    HASH_SIZE: ClassVar[int] = 16

    def __init__(self, model: Type[T], table: Table, versions: Table, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            model (Type[T]): The item model.
            table (Table): The items table.
            versions (Table): The versions table of the items.
            logger (Optional[Logger]): The mapper logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.model = model
        self.table = table
        self.versions = versions
        self.fields = list(model.model_fields)
        self.content_fields = [
            name for name in self.fields if name not in DATE_FIELDS and name not in model.SERVICE_FIELDS
        ]
        self.logger.debug(
            "Mapper of %s to the table %s ready (%d fields).", model.__name__, table.name, len(self.fields)
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def hash_key(self, key: str) -> bytes:
        """Hash a match key.

        Args:
            key (str): The match key (e.g. `url:https://...`).

        Returns:
            bytes: Its BLAKE2b digest of `HASH_SIZE` bytes.
        """
        return blake2b(key.encode("utf-8"), digest_size=self.HASH_SIZE).digest()

    def key_hashes(self, item: T) -> Tuple[bytes, bytes]:
        """Hash the most and the least reliable match keys of an item.

        Args:
            item (T): The item.

        Returns:
            Tuple[bytes, bytes]: The hash of its first match key,
                then of its last one (the same for a single key).
        """
        keys = item.match_keys()
        return self.hash_key(keys[0]), self.hash_key(keys[-1])

    def content(self, item: T) -> Dict[str, JsonValue]:
        """Get the content of an item, as stored in its versions.

        Args:
            item (T): The item.

        Returns:
            Dict[str, JsonValue]: The item without its dates and its categorization, as JSON.
        """
        content: Dict[str, JsonValue] = item.model_dump(mode="json", include=set(self.content_fields))
        return content

    def to_row(self, item: T, provider: str, fingerprint: Optional[bytes] = None) -> Dict[str, RowValue]:
        """Convert an item to the values of its row.

        Args:
            item (T): The item, dated.
            provider (str): The cloud provider of the item.
            fingerprint (Optional[bytes]): The hash of its content fields,
                when already computed.

        Returns:
            Dict[str, RowValue]: The column values, but the identifier,
                the first crawl and the revision.
        """
        service: Dict[str, JsonValue] = item.model_dump(mode="json", include=set(self.model.SERVICE_FIELDS))
        row: Dict[str, RowValue] = {**self.content(item), **service}
        for name in DATE_FIELDS:
            value = getattr(item, name)
            row[name] = value.value if isinstance(value, Enum) else value
        match_hash, name_hash = self.key_hashes(item)
        row.update(
            provider=provider,
            match_hash=match_hash,
            name_hash=name_hash,
            fingerprint=fingerprint or item.fingerprint_hash(),
        )
        return row

    def state_of(self, row: RowMapping) -> ItemState:
        """Get the history state of a stored item from its row, without building the item.

        Args:
            row (RowMapping): The row, with the date and fingerprint columns.

        Returns:
            ItemState: The dates and the content hash of the stored item.
        """
        return ItemState.model_validate({name: row[name] for name in (*DATE_FIELDS, "fingerprint")})

    def differs(self, values: Dict[str, RowValue], row: RowMapping) -> bool:
        """Tell whether the values of an item differ from its stored row.

        Args:
            values (Dict[str, RowValue]): The values of the item (see `to_row`).
            row (RowMapping): The stored row.

        Returns:
            bool: Whether a column would change.
        """
        return any(row[name] != value for name, value in values.items())

    def to_model(self, row: RowMapping) -> T:
        """Convert a row to its item.

        Args:
            row (RowMapping): The row, with a column per model field.

        Returns:
            T: The validated item.
        """
        return self.model.model_validate({name: row[name] for name in self.fields})

    def columns(self) -> List[Column[RowValue]]:
        """Get the columns read to build the items, with their identifier and match key hashes.

        Returns:
            List[Column[RowValue]]: The `id`, `match_hash`, `name_hash`
                columns, then a column per model field.
        """
        self.logger.debug("Reading the %d columns of %s.", len(self.fields) + 3, self.table.name)
        names = ["id", "match_hash", "name_hash", *self.fields]
        return [self.table.c[name] for name in names]
