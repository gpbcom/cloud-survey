from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Sequence, Tuple

# First Party Imports.
from models.companies.enums import CompanyIndicator, FinancialGranularity, IndicatorUnit
from models.companies.papers.paper_year_count import PaperYearCount
from models.companies.values.indicator_value import IndicatorValue

type YearKey = Tuple[str, CompanyIndicator, int]


class ResearchIndicators:
    """Turn the yearly counts of the patents and the papers into the research output series of the companies.

    Attributes:
        PATENTS (ClassVar[Tuple[CompanyIndicator, ...]]): The patents indicators.
        PAPERS (ClassVar[Tuple[CompanyIndicator, ...]]): The papers indicators derived from the stored papers.
        RATIOS (ClassVar[FrozenSet[CompanyIndicator]]): The indicators that are ratios, not counts.
        INPUTS (ClassVar[Dict[CompanyIndicator, str]]): How each indicator is counted.
        logger (Logger): The calculator logger.

    Notes:
        A year's point is dated on its 31 December. The patents are counted by priority year (the year of the
        invention), the grants by grant year, the papers by publication year (OpenAlex's own count).
    """

    PATENTS: ClassVar[Tuple[CompanyIndicator, ...]] = (
        CompanyIndicator.PATENT_FILINGS,
        CompanyIndicator.PATENT_FAMILIES,
        CompanyIndicator.PATENT_GRANTS,
        CompanyIndicator.PATENT_CITATIONS,
        CompanyIndicator.CITATIONS_PER_PATENT,
    )
    PAPERS: ClassVar[Tuple[CompanyIndicator, ...]] = (CompanyIndicator.PAPER_CITATIONS, CompanyIndicator.PAPER_FWCI)
    RATIOS: ClassVar[FrozenSet[CompanyIndicator]] = frozenset(
        {CompanyIndicator.CITATIONS_PER_PATENT, CompanyIndicator.PAPER_FWCI}
    )
    INPUTS: ClassVar[Dict[CompanyIndicator, str]] = {
        CompanyIndicator.PATENT_FILINGS: "publications by priority year (Google Patents)",
        CompanyIndicator.PATENT_FAMILIES: "families by priority year (Google Patents)",
        CompanyIndicator.PATENT_GRANTS: "patents granted in the year (Google Patents)",
        CompanyIndicator.PATENT_CITATIONS: "citations received by the publications of the priority year, pages read",
        CompanyIndicator.CITATIONS_PER_PATENT: "citations received per publication of the priority year, pages read",
        CompanyIndicator.PAPERS: "papers of the year (OpenAlex group_by publication_year)",
        CompanyIndicator.PAPER_CITATIONS: "citations received by the papers of the year (OpenAlex)",
        CompanyIndicator.PAPER_FWCI: "mean field-weighted citation impact of the papers of the year (OpenAlex)",
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the calculator.

        Args:
            logger (Optional[Logger]): The calculator logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _point(self, company: str, indicator: CompanyIndicator, year: int, value: float) -> IndicatorValue:
        """Build the point of a year.

        Args:
            company (str): The company.
            indicator (CompanyIndicator): The indicator.
            year (int): The year.
            value (float): The value.

        Returns:
            IndicatorValue: The point, dated on the 31 December.
        """
        return IndicatorValue(
            company=company,
            indicator=indicator,
            period_end=date(year, 12, 31),
            granularity=FinancialGranularity.YEAR,
            value=value,
            unit=IndicatorUnit.RATIO if indicator in self.RATIOS else IndicatorUnit.COUNT,
            inputs=self.INPUTS[indicator],
        )

    ############################
    # Publicly Exposed Methods #
    ############################

    def from_years(self, figures: Dict[YearKey, float]) -> List[IndicatorValue]:
        """Turn yearly figures into points.

        Args:
            figures (Dict[YearKey, float]): The value of each indicator, by company, indicator and year.

        Returns:
            List[IndicatorValue]: The points, by company, indicator and year.
        """
        points = [
            self._point(company, indicator, year, value)
            for (company, indicator, year), value in sorted(
                figures.items(), key=lambda item: (item[0][0], item[0][1].value, item[0][2])
            )
            if 1800 <= year <= 2200
        ]
        self.logger.debug("%d research indicator points.", len(points))
        return points

    def from_counts(self, counts: Sequence[PaperYearCount]) -> List[IndicatorValue]:
        """Turn OpenAlex's yearly paper counts into points.

        Args:
            counts (Sequence[PaperYearCount]): The counts.

        Returns:
            List[IndicatorValue]: A point per company and year.
        """
        return [
            self._point(count.company, CompanyIndicator.PAPERS, count.year, float(count.papers)) for count in counts
        ]
