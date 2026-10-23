from __future__ import annotations

# Standard Library Imports.
import math
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Tuple

# Third Party Imports.
import numpy
from numpy.typing import NDArray

# First Party Imports.
from analytics.drivers.correlation.benjamini_hochberg import BenjaminiHochberg
from analytics.drivers.correlation.spearman_correlation import SpearmanCorrelation
from analytics.markets.correlation.coverage_checker import CoverageChecker
from analytics.markets.correlation.series_granger import SeriesGranger
from analytics.markets.stocks.stock_table import StockTable
from models.markets.enums import Granularity
from models.markets.facts.price_point import PricePoint
from models.markets.series.lag_correlation import LagCorrelation
from models.markets.series.share_stock_result import ShareStockResult
from models.markets.values.market_share_value import MarketShareValue


class ShareStockCorrelation:
    """Correlate a company's share changes with the returns of its listing, period by period and lag by lag.

    Attributes:
        STEP (ClassVar[Dict[Granularity, int]]): The months of a period.
        MAX_LAG (ClassVar[Dict[Granularity, int]]): The most periods a series is shifted, both ways (a year).
        MIN_PAIRS (ClassVar[Dict[Granularity, int]]): The fewest period pairs a lag needs to get a correlation.
        BLOCK (ClassVar[Dict[Granularity, int]]): The periods of a block of the bootstrap (half a year).
        RESAMPLES (ClassVar[int]): The resamples of the bootstrap.
        GRANGER_LAGS (ClassVar[Dict[Granularity, int]]): The periods of past the Granger tests use.
        SEED (ClassVar[int]): The seed of the bootstrap, so that a result can be reproduced.
        spearman (SpearmanCorrelation): The rank correlation.
        multiple (BenjaminiHochberg): The q-values over the lags.
        granger (SeriesGranger): The lead test.
        coverage (CoverageChecker): The thresholds.
        table (StockTable): The month-end reduction, and the exchange rates.
        logger (Logger): The analysis logger.

    Notes:
        - The period is the shares': monthly for StatCounter, quarterly for the analyst releases (never
          interpolated). The returns follow: month-end or quarter-end closes in US dollars.
        - The share change is in points of share from one period to the next, the return is the log change of the
          close. Changes, not levels: two trending series always correlate in levels.
        - At lag `k` the share change of period `t` is paired with the return of period `t + k`: a positive `k` asks
          whether the market follows the share, a negative one whether the share follows the market.
        - The periods are autocorrelated, so the intervals come from a moving-block bootstrap (half a year per
          block) rather than from independent draws, and the q-values correct for the lags tested.
        - The analysis refuses to run below 36 months (16 quarters) of either series or with a gap over 3 periods,
          and says so.
    """

    STEP: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 1, Granularity.QUARTER: 3}
    MAX_LAG: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 12, Granularity.QUARTER: 4}
    MIN_PAIRS: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 24, Granularity.QUARTER: 12}
    BLOCK: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 6, Granularity.QUARTER: 2}
    RESAMPLES: ClassVar[int] = 400
    GRANGER_LAGS: ClassVar[Dict[Granularity, int]] = {Granularity.MONTH: 3, Granularity.QUARTER: 2}
    SEED: ClassVar[int] = 20261023

    def __init__(self, table: StockTable, logger: Optional[Logger] = None) -> None:
        """Initialize the analysis.

        Args:
            table (StockTable): The month-end reduction, and the exchange rates.
            logger (Optional[Logger]): The analysis logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.table = table
        self.spearman = SpearmanCorrelation()
        self.multiple = BenjaminiHochberg()
        self.granger = SeriesGranger()
        self.coverage = CoverageChecker()

    ############################
    # Internal Helpers Methods #
    ############################

    def _shift(self, period: date, months: int) -> date:
        """Move a period's first day by some months.

        Args:
            period (date): The first day of a month or a quarter.
            months (int): The months to move, negative to go back.

        Returns:
            date: The first day of the period reached.
        """
        index = period.year * 12 + period.month - 1 + months
        return date(index // 12, index % 12 + 1, 1)

    def _granularity(self, values: Sequence[MarketShareValue]) -> Granularity:
        """Choose the period of the analysis: monthly when the shares are, else quarterly.

        Args:
            values (Sequence[MarketShareValue]): The shares.

        Returns:
            Granularity: The month or the quarter.
        """
        return (
            Granularity.MONTH
            if any(value.granularity is Granularity.MONTH for value in values)
            else Granularity.QUARTER
        )

    def _closes(self, closes: Dict[date, float], granularity: Granularity) -> Dict[date, float]:
        """Reduce the month-end closes to the period's.

        Args:
            closes (Dict[date, float]): The month-end closes, by month.
            granularity (Granularity): The period.

        Returns:
            Dict[date, float]: The closes at the end of each period, keyed by the period's first day.
        """
        if granularity is Granularity.MONTH:
            return closes
        return {self._shift(month, -2): value for month, value in closes.items() if month.month % 3 == 0}

    def _changes(self, levels: Dict[date, float], step: int, log: bool) -> Dict[date, float]:
        """Turn levels into changes from the previous period (consecutive periods only).

        Args:
            levels (Dict[date, float]): The levels by period.
            step (int): The months of a period.
            log (bool): Whether the change is a log return rather than a difference.

        Returns:
            Dict[date, float]: The change of each period whose previous period has a level.
        """
        changes: Dict[date, float] = {}
        for period, level in levels.items():
            previous = levels.get(self._shift(period, -step))
            if previous is None:
                continue
            if log:
                if previous > 0 and level > 0:
                    changes[period] = math.log(level / previous)
            else:
                changes[period] = level - previous
        return changes

    def _bootstrap(
        self, x: NDArray[numpy.float64], y: NDArray[numpy.float64], block: int
    ) -> Tuple[Optional[float], Optional[float]]:
        """Get the 95% moving-block bootstrap interval of a rank correlation.

        Args:
            x (NDArray[numpy.float64]): The first series.
            y (NDArray[numpy.float64]): The second series, paired.
            block (int): The periods of a block.

        Returns:
            Tuple[Optional[float], Optional[float]]: The 2.5% and 97.5% quantiles, `None` without enough draws.
        """
        count = len(x)
        block = min(block, count)
        starts = count - block + 1
        generator = numpy.random.default_rng(self.SEED)
        draws: List[float] = []
        for _ in range(self.RESAMPLES):
            chosen = generator.integers(0, starts, size=math.ceil(count / block))
            index = numpy.concatenate([numpy.arange(start, start + block) for start in chosen])[:count]
            rho = self.spearman.rho(x[index], y[index])
            if rho is not None:
                draws.append(rho)
        if len(draws) < self.RESAMPLES // 2:
            return None, None
        return float(numpy.quantile(draws, 0.025)), float(numpy.quantile(draws, 0.975))

    def _lag(
        self, shares: Dict[date, float], returns: Dict[date, float], lag: int, granularity: Granularity
    ) -> LagCorrelation:
        """Correlate the share changes with the returns `lag` periods later.

        Args:
            shares (Dict[date, float]): The share changes by period.
            returns (Dict[date, float]): The returns by period.
            lag (int): The periods the returns follow.
            granularity (Granularity): The period.

        Returns:
            LagCorrelation: The correlation, empty below the fewest pairs.
        """
        months = lag * self.STEP[granularity]
        pairs = [
            (change, returns[self._shift(period, months)])
            for period, change in sorted(shares.items())
            if self._shift(period, months) in returns
        ]
        if len(pairs) < self.MIN_PAIRS[granularity]:
            return LagCorrelation(lag=lag, months=len(pairs))
        x = numpy.asarray([pair[0] for pair in pairs], dtype=numpy.float64)
        y = numpy.asarray([pair[1] for pair in pairs], dtype=numpy.float64)
        rho = self.spearman.rho(x, y)
        if rho is None:
            return LagCorrelation(lag=lag, months=len(pairs))
        low, high = self._bootstrap(x, y, self.BLOCK[granularity])
        return LagCorrelation(
            lag=lag, rho=rho, low=low, high=high, p_value=self.spearman.p_value(rho, len(pairs)), months=len(pairs)
        )

    def _longest_run(self, shares: Dict[date, float], returns: Dict[date, float], step: int) -> List[date]:
        """Find the longest run of consecutive periods with both a share change and a return.

        Args:
            shares (Dict[date, float]): The share changes by period.
            returns (Dict[date, float]): The returns by period.
            step (int): The months of a period.

        Returns:
            List[date]: The periods of the run, oldest first.
        """
        best: List[date] = []
        run: List[date] = []
        for period in sorted(set(shares) & set(returns)):
            run = [*run, period] if run and self._shift(run[-1], step) == period else [period]
            if len(run) > len(best):
                best = run
        return best

    ############################
    # Publicly Exposed Methods #
    ############################

    def period_shares(
        self, values: Sequence[MarketShareValue], company: str, granularity: Granularity = Granularity.MONTH
    ) -> Dict[date, float]:
        """Sum a company's labels into its share of each period.

        Args:
            values (Sequence[MarketShareValue]): The shares of one segment, area and device.
            company (str): The company.
            granularity (Granularity): The period kept (the others are left out).

        Returns:
            Dict[date, float]: Its share by period.
        """
        shares: Dict[date, float] = defaultdict(float)
        for value in values:
            if value.company == company and value.granularity is granularity:
                shares[value.period] += value.value
        return dict(sorted(shares.items()))

    def analyse(
        self,
        company: str,
        segment: str,
        area: str,
        device: str,
        values: Sequence[MarketShareValue],
        listing: Optional[str],
        prices: Sequence[PricePoint],
    ) -> ShareStockResult:
        """Correlate a company's share with its stock value.

        Args:
            company (str): The company.
            segment (str): The segment of the shares.
            area (str): The area of the shares.
            device (str): The devices of the shares.
            values (Sequence[MarketShareValue]): The shares of that segment, area and device.
            listing (Optional[str]): The company's primary listing, `None` when it has none.
            prices (Sequence[PricePoint]): The prices of that listing.

        Returns:
            ShareStockResult: The correlations by lag and the Granger p-values, or why they were not computed.
        """
        granularity = self._granularity(values)
        step = self.STEP[granularity]
        levels = self.period_shares(values, company, granularity)
        share_coverage = self.coverage.entry(f"{segment} / {area} / {device} / {company}", list(levels), granularity)
        empty = ShareStockResult(
            company=company,
            segment=segment,
            area=area,
            device=device,
            listing=listing,
            granularity=granularity,
            share_coverage=share_coverage,
            granger_lags=self.GRANGER_LAGS[granularity],
        )
        if listing is None:
            return empty.model_copy(update={"refusal": f"{company} has no listing: its value cannot be correlated."})
        ordered = sorted((point for point in prices if point.listing == listing), key=lambda point: point.day)
        usd = [
            (p.day, v)
            for p in ordered
            if (v := self.table.converter.convert(p.close, p.currency, "USD", p.day)) is not None
        ]
        closes = self._closes(self.table.month_ends(usd), granularity)
        stock_coverage = self.coverage.entry(listing, list(closes), granularity)
        empty = empty.model_copy(update={"stock_coverage": stock_coverage})
        unit = "months" if granularity is Granularity.MONTH else "quarters"
        for coverage in (share_coverage, stock_coverage):
            if not coverage.enough:
                reason = (
                    f"{coverage.key}: {coverage.points} {unit}, longest gap {coverage.longest_gap} "
                    f"(at least {CoverageChecker.MIN_POINTS[granularity]} {unit} and gaps of at most "
                    f"{CoverageChecker.MAX_GAP} are needed)."
                )
                self.logger.info("Share-stock correlation refused: %s", reason)
                return empty.model_copy(update={"refusal": reason})
        shares, returns = self._changes(levels, step, log=False), self._changes(closes, step, log=True)
        reach = self.MAX_LAG[granularity]
        lags = [self._lag(shares, returns, lag, granularity) for lag in range(-reach, reach + 1)]
        tested = [index for index, lag in enumerate(lags) if lag.p_value is not None]
        q_values = self.multiple.q_values([lags[index].p_value or 1.0 for index in tested])
        for index, q_value in zip(tested, q_values, strict=True):
            lags[index] = lags[index].model_copy(update={"q_value": q_value})
        run = self._longest_run(shares, returns, step)
        x = numpy.asarray([shares[period] for period in run], dtype=numpy.float64)
        y = numpy.asarray([returns[period] for period in run], dtype=numpy.float64)
        past = self.GRANGER_LAGS[granularity]
        result = empty.model_copy(
            update={
                "lags": lags,
                "share_leads_p": self.granger.p_value(y, x, past),
                "stock_leads_p": self.granger.p_value(x, y, past),
            }
        )
        self.logger.info(
            "Share-stock correlation of %s (%s, %s, %s): %d lags, Granger share->stock p=%s, stock->share p=%s.",
            company,
            segment,
            area,
            granularity.value,
            len(tested),
            result.share_leads_p,
            result.stock_leads_p,
        )
        return result
