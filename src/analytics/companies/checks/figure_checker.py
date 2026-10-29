from __future__ import annotations

# Standard Library Imports.
from bisect import bisect_left
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# First Party Imports.
from models.companies.enums import FigureScale, FinancialMetric
from models.companies.figures.reported_year import ReportedYear
from models.curated.enums import FigureCheck


class FigureChecker:
    """Check that a document states the figures researched from it, whatever the scale it writes them in.

    Attributes:
        FACTORS (ClassVar[Dict[FigureScale, Tuple[float, ...]]]): The factors turning an amount written in the
            company's scale into the ones a document may write it in (units, thousands, millions, billions).
        HEADCOUNT_FACTORS (ClassVar[Tuple[float, ...]]): The factors of a headcount (in units, or in thousands).
        RELATIVE (ClassVar[float]): The relative gap tolerated (a document's figure rounded to the scale researched).
        ABSOLUTE (ClassVar[float]): The absolute gap tolerated (the last digit of a figure written as an integer).
        logger (Logger): The checker logger.

    Notes:
        - A figure is found when a number of the document equals it, in one of the scales a document may write it
          in, within the rounding of either. The sign is left out (a document writes an expense positive or in
          parentheses).
        - A fiscal year matches when the document states every figure researched from it, mismatches when it
          states only some of them (the others are named in the check note), and is unparsed when the document
          gave no number or none of the figures (another format, or another document).
        - A small figure (an income tax of 72) is found in most long documents: a match proves the large figures
          more than the small ones.
    """

    FACTORS: ClassVar[Dict[FigureScale, Tuple[float, ...]]] = {
        FigureScale.UNITS: (1.0, 1e-3, 1e-6),
        FigureScale.THOUSANDS: (1.0, 1e3, 1e-3),
        FigureScale.MILLIONS: (1.0, 1e3, 1e6, 1e-3),
        FigureScale.BILLIONS: (1.0, 1e3, 1e6, 1e9),
    }
    HEADCOUNT_FACTORS: ClassVar[Tuple[float, ...]] = (1.0, 1e-3)
    RELATIVE: ClassVar[float] = 5e-4
    ABSOLUTE: ClassVar[float] = 0.5

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the checker.

        Args:
            logger (Optional[Logger]): The checker logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _near(self, numbers: Sequence[float], target: float) -> bool:
        """Tell whether a sorted list of numbers holds one near a target.

        Args:
            numbers (Sequence[float]): The numbers, sorted.
            target (float): The target.

        Returns:
            bool: Whether a number is within the tolerated gap of the target.
        """
        gap = max(self.ABSOLUTE, abs(target) * self.RELATIVE)
        index = bisect_left(numbers, target - gap)
        return index < len(numbers) and numbers[index] <= target + gap

    def _found(self, metric: FinancialMetric, value: float, scale: FigureScale, numbers: Sequence[float]) -> bool:
        """Tell whether a document states a researched figure.

        Args:
            metric (FinancialMetric): The statement line.
            value (float): The figure, in the company's scale (a headcount in units).
            scale (FigureScale): The company's scale.
            numbers (Sequence[float]): The numbers of the document, sorted.

        Returns:
            bool: Whether one of them is the figure, in a scale a document may write it in.
        """
        factors = self.HEADCOUNT_FACTORS if metric is FinancialMetric.EMPLOYEES else self.FACTORS[scale]
        return any(self._near(numbers, abs(value) * factor) for factor in factors)

    ############################
    # Publicly Exposed Methods #
    ############################

    def check(
        self, year: ReportedYear, scale: FigureScale, numbers: Sequence[float]
    ) -> Tuple[FigureCheck, Optional[str]]:
        """Check a researched fiscal year against the numbers of its document.

        Args:
            year (ReportedYear): The fiscal year and its figures.
            scale (FigureScale): The scale of the company's amounts.
            numbers (Sequence[float]): The numbers the document states, sorted.

        Returns:
            Tuple[FigureCheck, Optional[str]]: Whether the document states the figures, and the figures it does not
                state (a mismatch or a document read without any of them), `None` otherwise.
        """
        if not numbers:
            self.logger.warning("No number read from %s: fiscal year %d unparsed.", year.source, year.fiscal_year)
            return FigureCheck.UNPARSED, "the document gave no number (not read, or not text)"
        missing: List[str] = [
            metric.value for metric, value in year.figures.items() if not self._found(metric, value, scale, numbers)
        ]
        if not missing:
            self.logger.debug("Fiscal year %d matches its document.", year.fiscal_year)
            return FigureCheck.MATCH, None
        if len(missing) == len(year.figures):
            self.logger.warning("None of the figures of %d found in %s: unparsed.", year.fiscal_year, year.source)
            return FigureCheck.UNPARSED, "none of the figures found (another format or another document)"
        self.logger.info("Fiscal year %d: %d figures not found in its document.", year.fiscal_year, len(missing))
        return FigureCheck.MISMATCH, "not found: " + ", ".join(missing)
