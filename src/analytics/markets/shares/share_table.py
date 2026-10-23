from __future__ import annotations

# Standard Library Imports.
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

# First Party Imports.
from models.markets.series.share_series import ShareSeries
from models.markets.values.market_share_value import MarketShareValue


class ShareTable:
    """Fold the stored shares of a segment, an area and a device into the lines of the share chart.

    Attributes:
        OTHERS (ClassVar[str]): The name of the line of the other labels.
        logger (Logger): The table logger.

    Notes:
        - The labels of a company are summed (Chrome and Chromium make Google), the labels of no company go to
          "Others", with the companies beyond the top N.
        - The top N are the companies with the highest peak share in the window, not the latest one: a fallen
          leader (Nokia's Symbian) keeps its line.
    """

    OTHERS: ClassVar[str] = "Others"

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the table.

        Args:
            logger (Optional[Logger]): The table logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def series(
        self,
        values: Sequence[MarketShareValue],
        names: Dict[str, str],
        top: int = 8,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> List[ShareSeries]:
        """Build the lines of the top companies, then the others.

        Args:
            values (Sequence[MarketShareValue]): The shares of one segment, area, device and source.
            names (Dict[str, str]): The name of each company.
            top (int): The companies drawn on their own line.
            start (Optional[date]): Only the periods from this day.
            end (Optional[date]): Only the periods up to this day.

        Returns:
            List[ShareSeries]: The company lines by decreasing peak share, then "Others" when it has a value.
        """
        sums: Dict[Optional[str], Dict[date, float]] = defaultdict(lambda: defaultdict(float))
        labels: Dict[Optional[str], Set[str]] = defaultdict(set)
        estimate = False
        for value in values:
            if (start and value.period < start) or (end and value.period > end):
                continue
            sums[value.company][value.period] += value.value
            labels[value.company].add(value.label)
            estimate = estimate or value.estimate
        peaks: List[Tuple[float, str]] = sorted(
            ((max(by_period.values()), company) for company, by_period in sums.items() if company),
            reverse=True,
        )
        kept = [company for _, company in peaks[: max(0, top)]]
        others: Dict[date, float] = defaultdict(float)
        other_labels: Set[str] = set()
        for company, by_period in sums.items():
            if company in kept:
                continue
            other_labels |= labels[company]
            for period, share in by_period.items():
                others[period] += share
        lines = [
            ShareSeries(
                company=company,
                label=names.get(company, company),
                labels=sorted(labels[company]),
                points=[(period, round(share, 4)) for period, share in sums[company].items()],
                estimate=estimate,
            )
            for company in kept
        ]
        if others:
            lines.append(
                ShareSeries(
                    label=self.OTHERS,
                    labels=sorted(other_labels),
                    points=[(period, round(min(100.0, share), 4)) for period, share in others.items()],
                    estimate=estimate,
                )
            )
        self.logger.debug("%d share lines built from %d shares.", len(lines), len(values))
        return lines
