from __future__ import annotations

# Standard Library Imports.
from datetime import date
from logging import Logger, getLogger
from typing import Optional

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.compounding.results.fits.estimate import Estimate


class CardFormat:
    """Write the figures of the Service compounding cards.

    Attributes:
        POOLED (str): The name of the pooled fit.
        theme (Theme): The application theme (the provider names and colours).
        logger (Logger): The formatter logger.
    """

    POOLED = "Pooled"

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Initialize the formatter.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The formatter logger.
        """
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def provider(self, provider: Optional[CloudProvider]) -> str:
        """Name a provider.

        Args:
            provider (Optional[CloudProvider]): The provider, `None` for the pooled fit.

        Returns:
            str: Its display name.
        """
        return self.theme.provider_label(provider) if provider else self.POOLED

    def color(self, provider: Optional[CloudProvider]) -> str:
        """Get a provider's colour.

        Args:
            provider (Optional[CloudProvider]): The provider, `None` for the pooled fit.

        Returns:
            str: Its colour, `#rrggbb`.
        """
        return self.theme.provider_color(provider).name() if provider else self.theme.ACCENT

    def number(self, value: Optional[float], pattern: str = "{:.3g}") -> str:
        """Write a number.

        Args:
            value (Optional[float]): The number.
            pattern (str): Its format.

        Returns:
            str: The number, a dash when unknown.
        """
        return "-" if value is None else pattern.format(value)

    def estimate(self, estimate: Optional[Estimate]) -> str:
        """Write a coefficient and its interval.

        Args:
            estimate (Optional[Estimate]): The coefficient.

        Returns:
            str: `+0.59 [-0.79, +1.48]`, a star when the interval excludes zero, a dash when not fitted.
        """
        if estimate is None:
            return "-"
        text = f"{estimate.value:+.3g}"
        if estimate.low is not None and estimate.high is not None:
            text += f" [{estimate.low:+.3g}, {estimate.high:+.3g}]" + (" *" if estimate.significant() else "")
        return text

    def day(self, year: int) -> date:
        """Place a year on a time axis.

        Args:
            year (int): The year.

        Returns:
            date: Its middle.
        """
        return date(year, 7, 1)
