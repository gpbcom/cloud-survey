from __future__ import annotations

# Standard Library Imports.
import re
from datetime import date
from typing import ClassVar, Dict, Optional, Pattern, Tuple

# First Party Imports.
from models.markets.enums import Granularity


class PeriodLabel:
    """Read the period an analyst writes: `2Q26`, `Q4 2024`, `1Q 2025`, `third quarter of 2026` or `2022`.

    Attributes:
        QUARTER_FIRST (ClassVar[Pattern[str]]): The quarter written before the year, e.g. `2Q26`, `3Q 2025`.
        QUARTER_AFTER (ClassVar[Pattern[str]]): The quarter written after the `Q`, e.g. `Q4 2024`, `Q1'26`.
        QUARTER_WORDS (ClassVar[Pattern[str]]): The quarter written in words, e.g. `third quarter of 2026`.
        HALF (ClassVar[Pattern[str]]): A half-year, e.g. `1H26` or `H2 2025` (not read: it overlaps the quarters).
        YEAR (ClassVar[Pattern[str]]): A year alone, e.g. `2022`.
        BARE_QUARTER (ClassVar[Pattern[str]]): A quarter without its year, e.g. `Q2 NAND Flash Revenue`.
        ORDINALS (ClassVar[Dict[str, int]]): The quarter of each ordinal word.
    """

    QUARTER_FIRST: ClassVar[Pattern[str]] = re.compile(r"\b([1-4])Q\s?'?(\d{4}|\d{2})\b", re.IGNORECASE)
    QUARTER_AFTER: ClassVar[Pattern[str]] = re.compile(r"\bQ([1-4])\s?'?(\d{4}|\d{2})\b", re.IGNORECASE)
    QUARTER_WORDS: ClassVar[Pattern[str]] = re.compile(
        r"\b(first|second|third|fourth) quarter (?:of )?(\d{4})\b", re.IGNORECASE
    )
    HALF: ClassVar[Pattern[str]] = re.compile(r"\b(?:[12]H|H[12])\s?'?(?:\d{4}|\d{2})\b", re.IGNORECASE)
    YEAR: ClassVar[Pattern[str]] = re.compile(r"\b((?:19|20)\d{2})\b")
    BARE_QUARTER: ClassVar[Pattern[str]] = re.compile(
        r"\bQ([1-4])\b|\b([1-4])Q\b|\b(first|second|third|fourth) quarter\b", re.IGNORECASE
    )
    ORDINALS: ClassVar[Dict[str, int]] = {"first": 1, "second": 2, "third": 3, "fourth": 4}

    ############################
    # Internal Helpers Methods #
    ############################

    def _year(self, text: str) -> int:
        """Read a year written with two or four digits.

        Args:
            text (str): The year, e.g. `26` or `2026`.

        Returns:
            int: The year, two digits being read in the 2000s.
        """
        return int(text) if len(text) == 4 else 2000 + int(text)

    def _quarter(self, year: int, quarter: int) -> Tuple[date, Granularity]:
        """Build a quarter.

        Args:
            year (int): Its year.
            quarter (int): Its number, 1 to 4.

        Returns:
            Tuple[date, Granularity]: Its first day, and the quarter granularity.
        """
        return date(year, 3 * quarter - 2, 1), Granularity.QUARTER

    ############################
    # Publicly Exposed Methods #
    ############################

    def parse(self, text: str) -> Optional[Tuple[date, Granularity]]:
        """Read the first period of a text (a column header, a title).

        Args:
            text (str): The text.

        Returns:
            Optional[Tuple[date, Granularity]]: The first day of the period and its kind, `None` without a period or
                for a half-year.
        """
        found = self.QUARTER_FIRST.search(text)
        if found:
            return self._quarter(self._year(found.group(2)), int(found.group(1)))
        found = self.QUARTER_AFTER.search(text)
        if found:
            return self._quarter(self._year(found.group(2)), int(found.group(1)))
        found = self.QUARTER_WORDS.search(text)
        if found:
            return self._quarter(int(found.group(2)), self.ORDINALS[found.group(1).lower()])
        if self.HALF.search(text):
            return None
        found = self.YEAR.search(text)
        return (date(int(found.group(1)), 1, 1), Granularity.YEAR) if found else None

    def release(self, title: str, published: date) -> Optional[Tuple[date, Granularity]]:
        """Read the period of a press release title, a quarter without its year taking the latest one published.

        Args:
            title (str): The title, e.g. `Q2 NAND Flash Revenue Up 7.4%` or `Q4 Revenue Up 7.9%, Annual Total Hits
                US$111.54 Billion in 2023`.
            published (date): When the release was published.

        Returns:
            Optional[Tuple[date, Granularity]]: The first day of the period and its kind, `None` without a period.

        Notes:
            A quarter written without its year takes the year the title states, else the year of the last such
            quarter begun before the publication (a release of February on "Q4" is about the year before).
        """
        found = self.parse(title)
        if found is not None and found[1] is Granularity.QUARTER:
            return found
        bare = self.BARE_QUARTER.search(title)
        if bare is None:
            return found
        quarter = (
            int(bare.group(1) or bare.group(2))
            if (bare.group(1) or bare.group(2))
            else self.ORDINALS[bare.group(3).lower()]
        )
        year = found[0].year if found is not None else published.year
        if found is None and date(year, 3 * quarter - 2, 1) > published:
            year -= 1
        return self._quarter(year, quarter)
