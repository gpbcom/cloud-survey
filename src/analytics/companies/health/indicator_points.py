from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Optional, Sequence

# First Party Imports.
from analytics.companies.indicators.currency_rates import CurrencyRates
from models.companies.enums import CompanyIndicator, FinancialGranularity, IndicatorUnit
from models.companies.values.indicator_value import IndicatorValue


class IndicatorPoints:
    """Build the points of the indicator series: an amount also in US dollars, the inputs naming their sources.

    Attributes:
        INPUTS_LIMIT (ClassVar[int]): The longest inputs text stored.
        rates (CurrencyRates): Converts the amounts into US dollars.
        logger (Logger): The builder logger.

    Notes:
        The inputs of a point are its formula followed by the sources of its figures in brackets (e.g.
        `net-income / revenue [edgar:us-gaap:NetIncomeLoss, reported:estimate]`): an estimate or a run-rate among
        them stays recognisable on the chart.
    """

    INPUTS_LIMIT: ClassVar[int] = 300

    def __init__(self, rates: CurrencyRates, logger: Optional[Logger] = None) -> None:
        """Initialize the builder.

        Args:
            rates (CurrencyRates): Converts the amounts into US dollars.
            logger (Optional[Logger]): The builder logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.rates = rates

    ############################
    # Publicly Exposed Methods #
    ############################

    def ratio(self, numerator: Optional[float], denominator: Optional[float], factor: float = 1.0) -> Optional[float]:
        """Divide two figures, only over a positive denominator.

        Args:
            numerator (Optional[float]): The numerator.
            denominator (Optional[float]): The denominator.
            factor (float): The factor of the result (100 for a percentage).

        Returns:
            Optional[float]: The ratio, `None` when a figure lacks or the denominator is not positive.
        """
        if numerator is None or denominator is None or denominator <= 0:
            return None
        return numerator / denominator * factor

    def inputs(self, formula: str, sources: Sequence[str] = ()) -> str:
        """Write the inputs of a point: its formula, then the sources of its figures.

        Args:
            formula (str): How the point is computed.
            sources (Sequence[str]): Where its figures were read (each once, in their order).

        Returns:
            str: The inputs, at most `INPUTS_LIMIT` characters.
        """
        named = list(dict.fromkeys(source for source in sources if source))
        text = f"{formula} [{', '.join(named)}]" if named else formula
        return text[: self.INPUTS_LIMIT]

    def point(
        self,
        company: str,
        indicator: CompanyIndicator,
        granularity: FinancialGranularity,
        end: date,
        value: float,
        unit: IndicatorUnit,
        inputs: str,
        currency: Optional[str] = None,
    ) -> IndicatorValue:
        """Build a point of a series.

        Args:
            company (str): The company.
            indicator (CompanyIndicator): The indicator.
            granularity (FinancialGranularity): The period.
            end (date): The period end, or the day of a dated point.
            value (float): The value.
            unit (IndicatorUnit): The unit.
            inputs (str): How it was computed.
            currency (Optional[str]): The currency of an amount.

        Returns:
            IndicatorValue: The point, an amount also in US dollars when a rate is stored.
        """
        usd = self.rates.to_usd(value, currency, end) if unit is IndicatorUnit.CURRENCY else None
        return IndicatorValue(
            company=company,
            indicator=indicator,
            period_end=end,
            granularity=granularity,
            value=value,
            unit=unit,
            currency=currency if unit is IndicatorUnit.CURRENCY else None,
            value_usd=usd,
            inputs=inputs[: self.INPUTS_LIMIT],
        )
