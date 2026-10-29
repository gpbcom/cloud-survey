from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field


class Estimate(BaseModel):
    """A fitted coefficient with its 95% interval.

    Attributes:
        name (str): The coefficient, e.g. `foundations` or `size`.
        value (float): Its estimate.
        low (Optional[float]): The lower bound of its interval, `None` when not resampled.
        high (Optional[float]): The upper bound of its interval, `None` when not resampled.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=40, description="The coefficient.")
    value: float = Field(description="Its estimate.")
    low: Optional[float] = Field(default=None, description="The lower bound of its interval.")
    high: Optional[float] = Field(default=None, description="The upper bound of its interval.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def significant(self) -> bool:
        """Tell whether the interval excludes zero.

        Returns:
            bool: Whether both bounds are known and on the same side of zero.
        """
        if self.low is None or self.high is None:
            return False
        return self.low > 0 or self.high < 0
