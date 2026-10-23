from __future__ import annotations

# Standard Library Imports.
import re
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Pattern, Tuple

# Third Party Imports.
from scrapling.parser import Selector

# First Party Imports.
from models.markets.enums import Granularity
from models.markets.press.period_label import PeriodLabel

type TableShare = Tuple[str, date, Granularity, float]
type ReleaseTable = Tuple[str, List[TableShare]]


class PressTableReader:
    """Read the market share tables of an analyst press release: a company per row, a share column per period.

    Attributes:
        COMPANY_HEADERS (ClassVar[Tuple[str, ...]]): The first header cell of a table of companies.
        COMPLETE (ClassVar[Tuple[float, float]]): The range a complete share column sums to (the top N and Others).
        SKIPPED (ClassVar[Tuple[str, ...]]): The row labels that are no company (the totals, the headers again).
        RANK (ClassVar[Pattern[str]]): The rank written before a company, e.g. `1. ` or `3.`.
        NUMBER (ClassVar[Pattern[str]]): A share in a cell, e.g. `24.4%`.
        periods (PeriodLabel): Reads the period of a column header.
        logger (Logger): The reader logger.

    Notes:
        - The share columns are found by their header (`2Q26 Market Share`, `Q4 2024 Share`, `2022 Market Share
          (%)`): every one of them is read, so a release gives the quarter and the quarter a year before.
        - A table whose first header cell is not a company column (`Region`, `Form Factor`) is skipped, as the rows
          without a share. The caption is the first row when it is a single cell, else empty.
    """

    COMPANY_HEADERS: ClassVar[Tuple[str, ...]] = (
        "company",
        "companies",
        "vendor",
        "vendors",
        "brand",
        "brands",
        "supplier",
        "suppliers",
        "manufacturer",
        "foundry",
        "rank",
        "ranking",
    )
    COMPLETE: ClassVar[Tuple[float, float]] = (95.0, 105.0)
    SKIPPED: ClassVar[Tuple[str, ...]] = ("total", "total market", "company", "vendor", "brands", "grand total")
    RANK: ClassVar[Pattern[str]] = re.compile(r"^\s*\d+\s*[.)]\s*")
    NUMBER: ClassVar[Pattern[str]] = re.compile(r"(\d+(?:\.\d+)?)\s*%?")

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the reader.

        Args:
            logger (Optional[Logger]): The reader logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.periods = PeriodLabel()

    ############################
    # Internal Helpers Methods #
    ############################

    def _rows(self, table: Selector) -> List[List[str]]:
        """Read the cells of a table.

        Args:
            table (Selector): The table.

        Returns:
            List[List[str]]: The text of each cell, row by row.
        """
        return [
            [" ".join(str(cell.get_all_text(separator=" ", strip=True)).split()) for cell in row.css("th, td")]
            for row in table.css("tr")
        ]

    def _label(self, cell: str) -> str:
        """Clean a company cell.

        Args:
            cell (str): The cell.

        Returns:
            str: The company, without its rank and footnote marks.
        """
        return self.RANK.sub("", cell).strip().rstrip("*").strip()

    def _share(self, cell: str) -> Optional[float]:
        """Read a share cell.

        Args:
            cell (str): The cell, e.g. `24.4%`.

        Returns:
            Optional[float]: The share, `None` when the cell holds none.
        """
        found = self.NUMBER.search(cell.replace(",", ""))
        return float(found.group(1)) if found else None

    def _table(self, rows: List[List[str]]) -> Optional[ReleaseTable]:
        """Read the shares of a table.

        Args:
            rows (List[List[str]]): Its cells.

        Returns:
            Optional[ReleaseTable]: Its caption and its shares, `None` when it is no table of company shares.
        """
        caption = rows[0][0] if rows and len(rows[0]) == 1 else ""
        start = next(
            (index for index, row in enumerate(rows) if len(row) > 1 and any("share" in cell.lower() for cell in row)),
            None,
        )
        if start is None or rows[start][0].strip().lower() not in self.COMPANY_HEADERS:
            return None
        columns = []
        for index, header in enumerate(rows[start]):
            period = self.periods.parse(header) if "share" in header.lower() else None
            if period is not None:
                columns.append((index, period))
        if not columns:
            return None
        shares: List[TableShare] = []
        for row in rows[start + 1 :]:
            label = self._label(row[0]) if row else ""
            if not label or label.lower() in self.SKIPPED:
                continue
            for index, (day, granularity) in columns:
                value = self._share(row[index]) if index < len(row) else None
                if value is not None and value <= 100:
                    shares.append((label, day, granularity, value))
        return caption, shares

    ############################
    # Publicly Exposed Methods #
    ############################

    def read(self, fragment: str, complete: bool = False) -> List[ReleaseTable]:
        """Read every table of company shares of a release.

        Args:
            fragment (str): The HTML of the release body.
            complete (bool): Whether only the share columns summing to about 100% are kept (a firm whose tables list
                the others, as IDC's): a column summing otherwise is partial or misread.

        Returns:
            List[ReleaseTable]: The caption and the shares of each table of company shares.
        """
        found: List[ReleaseTable] = []
        for table in Selector(f"<div>{fragment}</div>").css("table"):
            read = self._table(self._rows(table))
            if read is None or not read[1]:
                continue
            caption, shares = read
            if complete:
                totals: Dict[date, float] = defaultdict(float)
                for _, day, _, value in shares:
                    totals[day] += value
                low, high = self.COMPLETE
                kept = {day for day, total in totals.items() if low <= total <= high}
                if len(kept) < len(totals):
                    self.logger.info(
                        "Incomplete share columns of the table %r left out: %d of %d.",
                        caption,
                        len(totals) - len(kept),
                        len(totals),
                    )
                shares = [share for share in shares if share[1] in kept]
            if shares:
                found.append((caption, shares))
        self.logger.debug("%d share tables read.", len(found))
        return found
