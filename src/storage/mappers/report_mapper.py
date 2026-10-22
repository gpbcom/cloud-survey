from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Dict, List, Optional

# Third Party Imports.
from sqlalchemy import Column, Table
from sqlalchemy.engine import RowMapping

# First Party Imports.
from models.stats.market_report import MarketReport
from storage.mappers.item_mapper import RowValue


class ReportMapper:
    """Convert the market reports to the rows of their table, and back.

    Attributes:
        table (Table): The market reports table, whose columns are named after the model fields.
        fields (List[str]): The model fields, each stored in the column of the same name.
        logger (Logger): The mapper logger.
    """

    def __init__(self, table: Table, logger: Optional[Logger] = None) -> None:
        """Initialize the mapper.

        Args:
            table (Table): The market reports table.
            logger (Optional[Logger]): The mapper logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.table = table
        self.fields = list(MarketReport.model_fields)
        self.logger.debug("Report mapper of the table %s ready.", table.name)

    ############################
    # Publicly Exposed Methods #
    ############################

    def to_row(self, report: MarketReport, source: str, position: int, crawl_id: int) -> Dict[str, RowValue]:
        """Convert a report to the values of its row.

        Args:
            report (MarketReport): The report.
            source (str): The statistics source (e.g. `synergy`).
            position (int): The position of the report in the statistics.
            crawl_id (int): The crawl writing the report.

        Returns:
            Dict[str, RowValue]: The column values, but the identifier.
        """
        self.logger.debug(
            "Report %s %s %s stored at position %d.", report.period, report.region.value, report.segment.value, position
        )
        row: Dict[str, RowValue] = report.model_dump(mode="json")
        row.update(published=report.published, source=source, position=position, crawl_id=crawl_id)
        return row

    def to_model(self, row: RowMapping) -> MarketReport:
        """Convert a row to its report.

        Args:
            row (RowMapping): The row, with a column per model field.

        Returns:
            MarketReport: The validated report.
        """
        self.logger.debug("Reading the report %s.", row["period"])
        return MarketReport.model_validate({name: row[name] for name in self.fields})

    def columns(self) -> List[Column[RowValue]]:
        """Get the columns read to build the reports.

        Returns:
            List[Column[RowValue]]: A column per model field.
        """
        self.logger.debug("Reading the %d report columns.", len(self.fields))
        return [self.table.c[name] for name in self.fields]
