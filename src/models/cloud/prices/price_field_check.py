from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Dict, List, Optional, Pattern, Sequence, Union

# Third Party Imports.
from pydantic import JsonValue

# First Party Imports.
from models.cloud.prices.exception import PriceCheckError

type RawValue = Union[JsonValue, Decimal, date, datetime]


class PriceFieldCheck:
    """Check the raw fields of the price models.

    Attributes:
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency (ISO 4217).
        URL (ClassVar[Pattern[str]]): The format of a source address.

    Notes:
        Each field of a price model has its own validator and its own error (`exception.py`): a check raises a
        `PriceCheckError` (the value and what was expected), which the validator of the field raises again as the
        error of that field.
    """

    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    URL: ClassVar[Pattern[str]] = re.compile(r"^https?://\S+$")

    ############################
    # Publicly Exposed Methods #
    ############################

    def text(
        self,
        value: RawValue,
        maximum: int,
        minimum: int = 1,
        optional: bool = False,
        collapse: bool = True,
    ) -> Optional[str]:
        """Check a text.

        Args:
            value (RawValue): The raw value.
            maximum (int): Its most characters.
            minimum (int): Its fewest characters.
            optional (bool): Whether it may be missing (`None` or blank).
            collapse (bool): Whether its inner spaces are collapsed (else it is only trimmed).

        Returns:
            Optional[str]: The text, `None` when optional and missing.

        Raises:
            PriceCheckError: If it is not a text of `minimum` to `maximum` characters.
        """
        if value is None and optional:
            return None
        if not isinstance(value, str):
            raise PriceCheckError(repr(value), f"a text of {minimum} to {maximum} characters")
        text = " ".join(value.split()) if collapse else value.strip()
        if not text and optional:
            return None
        if not minimum <= len(text) <= maximum:
            raise PriceCheckError(text, f"a text of {minimum} to {maximum} characters")
        return text

    def number(
        self,
        value: RawValue,
        positive: bool = False,
        optional: bool = False,
    ) -> Optional[Decimal]:
        """Check a non-negative decimal number.

        Args:
            value (RawValue): The raw value (a number, or its text).
            positive (bool): Whether it must be more than 0.
            optional (bool): Whether it may be missing.

        Returns:
            Optional[Decimal]: The number, `None` when optional and missing.

        Raises:
            PriceCheckError: If it is not a finite number, or is negative (or zero when positive).
        """
        expected = "a number above 0" if positive else "a number from 0"
        if value is None and optional:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            raise PriceCheckError(repr(value), expected)
        try:
            number = Decimal(str(value).strip())
        except InvalidOperation as e:
            raise PriceCheckError(repr(value), expected) from e
        if not number.is_finite() or number < 0 or (positive and number == 0):
            raise PriceCheckError(repr(value), expected)
        return number

    def whole(self, value: RawValue, positive: bool = False, optional: bool = False) -> Optional[int]:
        """Check a non-negative whole number.

        Args:
            value (RawValue): The raw value.
            positive (bool): Whether it must be more than 0.
            optional (bool): Whether it may be missing.

        Returns:
            Optional[int]: The number, `None` when optional and missing.

        Raises:
            PriceCheckError: If it is not a whole number, or is negative (or zero when positive).
        """
        expected = "a whole number above 0" if positive else "a whole number from 0"
        if value is None and optional:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0 or (positive and value == 0):
            raise PriceCheckError(repr(value), expected)
        return value

    def choice(self, value: RawValue, choices: Sequence[str], optional: bool = False) -> Optional[str]:
        """Check one of a list of values (an enum member).

        Args:
            value (RawValue): The raw value.
            choices (Sequence[str]): The values allowed.
            optional (bool): Whether it may be missing.

        Returns:
            Optional[str]: The value, `None` when optional and missing.

        Raises:
            PriceCheckError: If it is not one of the values.
        """
        if value is None and optional:
            return None
        text = str(value).strip() if isinstance(value, str) else None
        if text not in choices:
            raise PriceCheckError(repr(value), "one of " + ", ".join(choices))
        return text

    def currency(self, value: RawValue, optional: bool = True) -> Optional[str]:
        """Check a currency: an ISO 4217 code, upper-cased.

        Args:
            value (RawValue): The raw value.
            optional (bool): Whether it may be missing.

        Returns:
            Optional[str]: The code, `None` when optional and missing.

        Raises:
            PriceCheckError: If it is not three letters.
        """
        if value is None and optional:
            return None
        code = value.strip().upper() if isinstance(value, str) else ""
        if not self.CURRENCY.match(code):
            raise PriceCheckError(repr(value), "an ISO 4217 currency code")
        return code

    def url(self, value: RawValue) -> str:
        """Check a source address: an http or https URL.

        Args:
            value (RawValue): The raw value.

        Returns:
            str: The URL, trimmed.

        Raises:
            PriceCheckError: If it is not an http or https URL of at most 2048 characters.
        """
        url = value.strip() if isinstance(value, str) else ""
        if not self.URL.match(url) or len(url) > 2048:
            raise PriceCheckError(repr(value), "an http or https URL")
        return url

    def day(self, value: RawValue, optional: bool = True) -> Optional[date]:
        """Check a day: a date, or its ISO text.

        Args:
            value (RawValue): The raw value.
            optional (bool): Whether it may be missing.

        Returns:
            Optional[date]: The day, `None` when optional and missing.

        Raises:
            PriceCheckError: If it is not a date.
        """
        if value is None and optional:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str):
            raise PriceCheckError(repr(value), "a date, YYYY-MM-DD")
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError as e:
            raise PriceCheckError(repr(value), "a date, YYYY-MM-DD") from e

    def moment(self, value: RawValue, optional: bool = True) -> Optional[datetime]:
        """Check a moment: a time-zone aware date and time, or its ISO text.

        Args:
            value (RawValue): The raw value.
            optional (bool): Whether it may be missing.

        Returns:
            Optional[datetime]: The moment, `None` when optional and missing.

        Raises:
            PriceCheckError: If it is not a date and time with its time zone.
        """
        if value is None and optional:
            return None
        moment: Optional[datetime] = value if isinstance(value, datetime) else None
        if isinstance(value, str):
            try:
                moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            except ValueError as e:
                raise PriceCheckError(repr(value), "a date and time with its time zone") from e
        if moment is None or moment.tzinfo is None:
            raise PriceCheckError(repr(value), "a date and time with its time zone")
        return moment

    def flag(self, value: RawValue) -> bool:
        """Check a flag.

        Args:
            value (RawValue): The raw value.

        Returns:
            bool: The flag.

        Raises:
            PriceCheckError: If it is not a boolean.
        """
        if not isinstance(value, bool):
            raise PriceCheckError(repr(value), "true or false")
        return value

    def mapping(self, value: RawValue) -> Dict[str, JsonValue]:
        """Check a JSON object.

        Args:
            value (RawValue): The raw value.

        Returns:
            Dict[str, JsonValue]: The object.

        Raises:
            PriceCheckError: If it is not an object with text keys.
        """
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise PriceCheckError(repr(value)[:200], "an object with text keys")
        return value

    def items(self, value: RawValue) -> List[JsonValue]:
        """Check a list.

        Args:
            value (RawValue): The raw value.

        Returns:
            List[JsonValue]: The items.

        Raises:
            PriceCheckError: If it is not a list.
        """
        if not isinstance(value, (list, tuple)):
            raise PriceCheckError(repr(value)[:200], "a list")
        return list(value)
