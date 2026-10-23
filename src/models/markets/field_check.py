from __future__ import annotations

# Standard Library Imports.
import math
from datetime import date, datetime
from typing import List, Optional, Sequence, Tuple, Union

# Third Party Imports.
from pydantic import JsonValue

# First Party Imports.
from models.markets.exception import (
    InvalidMarketChoiceError,
    InvalidMarketDateError,
    InvalidMarketFlagError,
    InvalidMarketListError,
    InvalidMarketNumberError,
    InvalidMarketTextError,
)

type RawValue = Union[JsonValue, date]


class MarketFieldCheck:
    """Check the raw fields of the markets models, raising a markets error on a value pydantic would reject.

    Notes:
        - Every field validator of `models.markets` calls one of these checks in `before` mode, so a bad value of
          the YAML, a crawl or the database is reported with what it is and what was expected (a
          `MarketsModelError`, wrapped by pydantic in its `ValidationError`), rather than by a generic type error.
        - A check returns the value cleaned (trimmed, converted), which pydantic then validates as usual.
    """

    ############################
    # Internal Helpers Methods #
    ############################

    def _range(self, low: Optional[float], high: Optional[float], strict_low: bool, integer: bool) -> str:
        """Describe a range.

        Args:
            low (Optional[float]): The lowest value, if any.
            high (Optional[float]): The highest value, if any.
            strict_low (bool): Whether the lowest value is excluded.
            integer (bool): Whether a whole number is expected.

        Returns:
            str: The range, e.g. `a number from 0 to 100`.
        """
        noun = "a whole number" if integer else "a number"
        if low is not None and high is not None:
            return f"{noun} from {low:g}{' (excluded)' if strict_low else ''} to {high:g}"
        if low is not None:
            return f"{noun} {'above' if strict_low else 'of at least'} {low:g}"
        return f"{noun} of at most {high:g}" if high is not None else f"a finite {noun}"

    ############################
    # Publicly Exposed Methods #
    ############################

    def text(
        self,
        value: RawValue,
        kind: str,
        maximum: int,
        minimum: int = 1,
        optional: bool = False,
        collapse: bool = True,
    ) -> Optional[str]:
        """Check a text.

        Args:
            value (RawValue): The raw value.
            kind (str): What the text is.
            maximum (int): Its most characters.
            minimum (int): Its fewest characters.
            optional (bool): Whether it may be missing (`None` or blank).
            collapse (bool): Whether its inner spaces are collapsed (else it is only trimmed).

        Returns:
            Optional[str]: The text, trimmed, `None` when optional and missing.

        Raises:
            InvalidMarketTextError: If it is not a string, or is too short or too long.
        """
        expected = f"a text of {minimum} to {maximum} characters"
        if value is None and optional:
            return None
        if not isinstance(value, str):
            raise InvalidMarketTextError(kind, repr(value), expected)
        text = " ".join(value.split()) if collapse else value.strip()
        if not text and optional:
            return None
        if not minimum <= len(text) <= maximum:
            raise InvalidMarketTextError(kind, text, expected)
        return text

    def number(
        self,
        value: RawValue,
        kind: str,
        low: Optional[float] = None,
        high: Optional[float] = None,
        strict_low: bool = False,
        optional: bool = False,
        integer: bool = False,
    ) -> Optional[float]:
        """Check a number.

        Args:
            value (RawValue): The raw value (a number, or a text holding one).
            kind (str): What the number is.
            low (Optional[float]): The lowest value, if any.
            high (Optional[float]): The highest value, if any.
            strict_low (bool): Whether the lowest value is excluded.
            optional (bool): Whether it may be `None`.
            integer (bool): Whether a whole number is expected (it is then returned as an integer).

        Returns:
            Optional[float]: The number (an `int` when whole numbers are expected), `None` when optional and missing.

        Raises:
            InvalidMarketNumberError: If it is not a finite number, not whole when expected, or out of range.
        """
        expected = self._range(low, high, strict_low, integer)
        if value is None and optional:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise InvalidMarketNumberError(kind, repr(value), expected)
        try:
            number = float(value.strip().rstrip("%")) if isinstance(value, str) else float(value)
        except ValueError as e:
            raise InvalidMarketNumberError(kind, repr(value), expected) from e
        if not math.isfinite(number) or (integer and not number.is_integer()):
            raise InvalidMarketNumberError(kind, repr(value), expected)
        too_low = low is not None and (number <= low if strict_low else number < low)
        if too_low or (high is not None and number > high):
            raise InvalidMarketNumberError(kind, repr(value), expected)
        return int(number) if integer else number

    def choice(self, value: RawValue, kind: str, choices: Sequence[str], optional: bool = False) -> Optional[str]:
        """Check a value among allowed ones (an enum value).

        Args:
            value (RawValue): The raw value (an enum member is a text).
            kind (str): What the value is.
            choices (Sequence[str]): The allowed values.
            optional (bool): Whether it may be `None`.

        Returns:
            Optional[str]: The value, trimmed, `None` when optional and missing.

        Raises:
            InvalidMarketChoiceError: If it is not one of the allowed values.
        """
        if value is None and optional:
            return None
        text = value.strip() if isinstance(value, str) else None
        if text is None or text not in choices:
            raise InvalidMarketChoiceError(kind, repr(value), list(choices))
        return text

    def day(self, value: RawValue, kind: str, optional: bool = False) -> Optional[date]:
        """Check a date.

        Args:
            value (RawValue): The raw value: a date, a date-time (its day is kept) or an ISO text.
            kind (str): What the date is.
            optional (bool): Whether it may be `None`.

        Returns:
            Optional[date]: The date, `None` when optional and missing.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        if value is None and optional:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value.strip()[:10])
            except ValueError as e:
                raise InvalidMarketDateError(kind, value) from e
        raise InvalidMarketDateError(kind, repr(value))

    def iso_day(self, value: RawValue, kind: str, optional: bool = False) -> Optional[str]:
        """Check a date, and write it as ISO text (what a field validator hands pydantic).

        Args:
            value (RawValue): The raw value: a date, a date-time (its day is kept) or an ISO text.
            kind (str): What the date is.
            optional (bool): Whether it may be `None`.

        Returns:
            Optional[str]: The date, `YYYY-MM-DD`, `None` when optional and missing.

        Raises:
            InvalidMarketDateError: If it is not a date.
        """
        day = self.day(value, kind, optional)
        return day.isoformat() if day else None

    def flag(self, value: RawValue, kind: str) -> bool:
        """Check a yes-or-no value.

        Args:
            value (RawValue): The raw value.
            kind (str): What the flag is.

        Returns:
            bool: The flag.

        Raises:
            InvalidMarketFlagError: If it is not a boolean.
        """
        if not isinstance(value, bool):
            raise InvalidMarketFlagError(kind, repr(value))
        return value

    def items(self, value: RawValue, kind: str, expected: str) -> List[JsonValue]:
        """Check a list.

        Args:
            value (RawValue): The raw value (a list or a tuple).
            kind (str): What the list is.
            expected (str): What its items are.

        Returns:
            List[JsonValue]: The items.

        Raises:
            InvalidMarketListError: If it is not a list.
        """
        if not isinstance(value, (list, tuple)):
            raise InvalidMarketListError(kind, f"a list of {expected}")
        return list(value)

    def points(self, value: RawValue, kind: str, positive: bool = False) -> List[Tuple[date, float]]:
        """Check the points of a series: `(date, value)` pairs.

        Args:
            value (RawValue): The raw points.
            kind (str): What the points are.
            positive (bool): Whether the values must be above zero.

        Returns:
            List[Tuple[date, float]]: The points, sorted by date.

        Raises:
            InvalidMarketListError: If it is not a list of pairs, or a pair holds no date or no finite number.
        """
        expected = "(date, number) pairs" + (", the numbers above zero" if positive else "")
        points: List[Tuple[date, float]] = []
        for item in self.items(value, kind, expected):
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise InvalidMarketListError(kind, f"a list of {expected}")
            try:
                day = self.day(item[0], kind)
                number = self.number(item[1], kind, low=0.0 if positive else None, strict_low=positive)
            except (InvalidMarketDateError, InvalidMarketNumberError) as e:
                raise InvalidMarketListError(kind, f"a list of {expected} ({e.message})") from e
            if day is None or number is None:
                raise InvalidMarketListError(kind, f"a list of {expected}")
            points.append((day, number))
        return sorted(points, key=lambda point: point[0])
