from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional

# First Party Imports.
from analytics.series.axis_rules import AxisRules
from models.storage.enums import DatasetKind
from models.storage.pages.item_query import ItemQuery
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, MatrixCell
from models.trends.matrix.metric_matrix import MetricMatrix
from storage.storage import Storage


class MatrixLoader:
    """Read the cells of a matrix chart of the marketplaces: the job of a matrix storage request.

    Attributes:
        rules (AxisRules): The chart rules.
        logger (Logger): The loader logger.

    Notes:
        A mix of bars always shows the share of each column in its row.
    """

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the loader.

        Args:
            logger (Optional[Logger]): The loader logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.rules = AxisRules(self.logger)

    ############################
    # Publicly Exposed Methods #
    ############################

    async def load(self, storage: Storage, axes: ChartAxes, query: ItemQuery) -> MetricMatrix:
        """Read the cells of a matrix chart.

        Args:
            storage (Storage): The open storage.
            axes (ChartAxes): The chart axes (repaired when invalid).
            query (ItemQuery): The filters of the marketplace software.

        Returns:
            MetricMatrix: The cells of the largest rows and columns, empty for a chart of series (logged).

        Raises:
            StorageReadError: If the software cannot be counted.
        """
        axes = self.rules.repair(axes)
        if not axes.chart.is_matrix:
            self.logger.warning("The %s chart is not a matrix: it has no cells.", axes.chart.value)
            return MetricMatrix()
        if axes.cell.publisher_pairs:
            matrix = await storage.matrices.publisher_overlap(query, axes.cell is MatrixCell.OVERLAP, axes.top)
        else:
            cell = MatrixCell.ROW_SHARE if axes.chart is ChartKind.MIX else axes.cell
            kind = axes.scope.dataset or DatasetKind.MARKETPLACE
            matrix = await storage.matrices.cells(query, axes.series_by, axes.columns, cell, axes.top, kind)
        self.logger.debug(
            "%s matrix loaded: %d rows by %d columns.", axes.cell.value, len(matrix.rows), len(matrix.columns)
        )
        return matrix
