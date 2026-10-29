from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Awaitable, Callable, Dict, List, Optional, Set, Tuple

# Third Party Imports.
from pydantic import BaseModel

# First Party Imports.
from models.storage.records.enums import RecordSort
from models.storage.records.record_query import RecordQuery
from storage.storage import Storage

type RecordReader = Callable[[Storage, RecordQuery], Awaitable[Tuple[List[BaseModel], Optional[int]]]]


class RecordLayout:
    """What a table of stored records shows: its columns, how they are sorted and how a record is read and written.

    Attributes:
        headers (List[Tuple[str, str]]): The title and the tooltip of each column.
        sorts (Dict[int, RecordSort]): The order of each sortable column (the other columns are not sortable).
        default (int): The column the records are sorted by at first (descending).
        numeric (Set[int]): The columns aligned right.
        wide (Set[int]): The columns of long texts (titles, names), shown wider.
        reader (RecordReader): Reads a page of records: the records, then their count when it was asked.
        cells (Callable[[BaseModel], List[str]]): Writes the text of each column of a record.
        link (Callable[[BaseModel], Optional[str]]): Gets the page a record is opened at.
        logger (Logger): The layout logger.
    """

    def __init__(
        self,
        headers: List[Tuple[str, str]],
        sorts: Dict[int, RecordSort],
        default: int,
        numeric: Set[int],
        wide: Set[int],
        reader: RecordReader,
        cells: Callable[[BaseModel], List[str]],
        link: Callable[[BaseModel], Optional[str]],
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the layout.

        Args:
            headers (List[Tuple[str, str]]): The title and the tooltip of each column.
            sorts (Dict[int, RecordSort]): The order of each sortable column.
            default (int): The column the records are sorted by at first.
            numeric (Set[int]): The columns aligned right.
            wide (Set[int]): The columns of long texts, shown wider.
            reader (RecordReader): Reads a page of records.
            cells (Callable[[BaseModel], List[str]]): Writes the text of each column of a record.
            link (Callable[[BaseModel], Optional[str]]): Gets the page a record is opened at.
            logger (Optional[Logger]): The layout logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.headers = headers
        self.sorts = sorts
        self.default = default
        self.numeric = numeric
        self.wide = wide
        self.reader = reader
        self.cells = cells
        self.link = link
        self.logger.debug("Record layout of %d columns, %d sortable.", len(headers), len(sorts))
