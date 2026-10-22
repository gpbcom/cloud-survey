from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional

# First Party Imports.
from analytics.series.time_axis import TimeAxis
from models.trends.enums import ChartMetric, MetricKind, MetricUnit


class AxisFormatter:
    """Write the values of the chart axes, tooltips and cells for people: units, separators, compact numbers.

    Attributes:
        CURRENCY_SYMBOLS (ClassVar[Dict[str, str]]): The symbol of each currency.
        time (TimeAxis): The time axis, naming the moments.
        logger (Logger): The formatter logger.
    """

    CURRENCY_SYMBOLS: ClassVar[Dict[str, str]] = {"USD": "$", "EUR": "€"}

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the formatter.

        Args:
            logger (Optional[Logger]): The formatter logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.time = TimeAxis(self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    def _number(self, value: float, decimals: int) -> str:
        """Write a number with thousands separators, without a useless decimal.

        Args:
            value (float): The number.
            decimals (int): The largest number of decimals.

        Returns:
            str: e.g. `1,234` or `12.5`.
        """
        text = f"{value:,.{decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return "0" if text in ("-0", "") else text

    def _count(self, value: float, compact: bool) -> str:
        """Write a count, shortened with `k` or `M` when compact.

        Args:
            value (float): The count.
            compact (bool): Whether the large counts are shortened.

        Returns:
            str: e.g. `1,234`, `12.3k` or `1.2M`.
        """
        size = abs(value)
        if compact and size >= 1_000_000:
            return f"{self._number(value / 1_000_000, 1)}M"
        if compact and size >= 10_000:
            return f"{self._number(value / 1_000, 1)}k"
        return self._number(value, 0 if value == round(value) else 1)

    ############################
    # Publicly Exposed Methods #
    ############################

    def value(
        self,
        unit: MetricUnit,
        value: float,
        currency: Optional[str] = None,
        step: Optional[float] = None,
        compact: bool = True,
    ) -> str:
        """Write a value with its unit.

        Args:
            unit (MetricUnit): The unit.
            value (float): The value.
            currency (Optional[str]): The currency of an amount, `None` when unknown or mixed.
            step (Optional[float]): The grid step of the axis, to choose the decimals (`None` outside the axes).
            compact (bool): Whether the large counts are shortened.

        Returns:
            str: e.g. `1,234`, `12.3k`, `28%`, `$143.4bn`, `#3` or `112`.
        """
        decimals = 1 if step is None or step < 1 else 0
        match unit:
            case MetricUnit.PERCENT:
                return f"{self._number(value, decimals)}%"
            case MetricUnit.BILLIONS:
                symbol = self.CURRENCY_SYMBOLS.get(currency or "", "")
                return f"{symbol}{self._number(value, 1)}bn"
            case MetricUnit.INDEX:
                return self._number(value, decimals)
            case MetricUnit.RANK:
                return f"#{round(value)}"
            case MetricUnit.DATE:
                return self.time.label(ChartMetric.PUBLISHED, value)
            case _:
                return self._count(value, compact)

    def x_label(
        self, metric: ChartMetric, value: float, label: Optional[str] = None, step: Optional[float] = None
    ) -> str:
        """Write an x value: a moment named the way its axis counts time, or a value with its unit.

        Args:
            metric (ChartMetric): The metric of the x axis.
            value (float): The x value.
            label (Optional[str]): The name of the point, e.g. its period, `None` to name it from its value.
            step (Optional[float]): The grid step of a numeric axis.

        Returns:
            str: e.g. `2025H1`, `2026Q2`, `12 Mar 2026` or `30%`.
        """
        if metric.kind is MetricKind.TIME:
            return label or self.time.label(metric, value)
        return self.value(metric.unit, value, step=step)
