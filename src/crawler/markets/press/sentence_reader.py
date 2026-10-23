from __future__ import annotations

# Standard Library Imports.
import re
from collections import defaultdict
from datetime import date
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Pattern, Sequence, Tuple

# First Party Imports.
from crawler.markets.press.table_reader import TableShare
from models.markets.enums import Granularity
from models.markets.press.period_label import PeriodLabel


class PressSentenceReader:
    """Read the market shares a press release states in its sentences, e.g. "TSMC … capturing a 72.5% market share".

    Attributes:
        SENTENCE (ClassVar[Pattern[str]]): Where a sentence ends: a full stop followed by a capital.
        SHARE_AFTER (ClassVar[Pattern[str]]): A share written before the word, e.g. `38.6% market share`.
        SHARE_BEFORE (ClassVar[Pattern[str]]): A share written after the word, at most three words later, e.g.
            `market share slipped slightly to 32.7%`.
        PERIOD_AFTER (ClassVar[Pattern[str]]): The period stated right after a share, e.g. ` in 2009`.
        PERIOD_ANY (ClassVar[Pattern[str]]): A period stated anywhere, e.g. `2Q26` or `2009`.
        GENERIC (ClassVar[Pattern[str]]): A share introduced by "the" ("the own brand market share") or owned by a
            group or a process node ("Taiwanese vendors' share", "this node's revenue share"), which belongs to no
            company in particular.
        GROUP (ClassVar[Pattern[str]]): The words of a group of companies ("Korean vendors", "top 5 foundries"): a
            sentence naming no company but a group states the group's share.
        CHANGE (ClassVar[Pattern[str]]): The words following a share that is a change ("0.5% market share growth").
        HIGHEST (ClassVar[float]): The highest share read (a share of 99% or more is a total or a growth).
        TOLERANCE (ClassVar[float]): How far above 100% the shares of a period may sum (rounding).
        periods (PeriodLabel): Reads the periods.
        logger (Logger): The reader logger.

    Notes:
        - A share goes to the company named last before it in the sentence or, when the sentence names none ("Its
          market share edged up to 5.4%", "revenue surged…, boosting market share to 38.7%"), to the company named
          last in the sentences before. A share introduced by "the" ("the own brand market share grew to 17.4%"),
          owned by a group ("Korean vendors' market share reached 63.7%"), stated in a sentence naming a group but no
          company ("these two South Korean manufacturers account for 70.8%"), followed by a change word ("0.5% market
          share growth") or of 99% or more belongs to no company and is left out.
        - Only stated shares are read: a change ("increased 9.6%", "0.3 percentage points") never matches the two
          wordings. The period is the one stated right after the share ("with 6.9% market share in 2009"), else the
          last one stated before it in the sentence ("in 2009 yearly basis, Samsung … 37.9%"), else the release's.
        - The first share of a company and period wins (the later ones compare with earlier quarters). A period
          whose shares sum above 100% was misread: it is left out, with a warning.
    """

    SENTENCE: ClassVar[Pattern[str]] = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
    SHARE_AFTER: ClassVar[Pattern[str]] = re.compile(
        r"(\d+(?:\.\d+)?)\s*%\s+(?:(?:global|worldwide|market|revenue|foundry|sales)\s+)*share", re.IGNORECASE
    )
    SHARE_BEFORE: ClassVar[Pattern[str]] = re.compile(
        r"share\s+(?:[a-z]+\s+){0,3}?(?:of|at|to|was|is|reached|reaching|stood at|stands at)\s+"
        r"(?:(?:a|an|new|record|high|of|nearly|about|around|approximately|roughly|over|just|some)\s+){0,4}"
        r"(\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    )
    PERIOD_AFTER: ClassVar[Pattern[str]] = re.compile(
        r"^\s*(?:in|for|during)\s+(?:the\s+)?([1-4]Q\s?'?\d{2,4}|Q[1-4]\s?'?\d{2,4}|(?:19|20)\d{2})\b", re.IGNORECASE
    )
    PERIOD_ANY: ClassVar[Pattern[str]] = re.compile(
        r"\b(?:[1-4]Q\s?'?\d{2,4}|Q[1-4]\s?'?\d{2,4}|"
        r"(?:first|second|third|fourth) quarter (?:of )?\d{4}|(?:19|20)\d{2})\b",
        re.IGNORECASE,
    )
    GENERIC: ClassVar[Pattern[str]] = re.compile(
        r"(?:\bthe\s+(?:[a-z-]+\s+){0,3}|\b(?:vendors|makers|brands|suppliers|companies|players|manufacturers|"
        r"foundries|nodes?|process(?:es)?)['\u2019]?s?\s+(?:[a-z-]+\s+){0,2})$",
        re.IGNORECASE,
    )
    GROUP: ClassVar[Pattern[str]] = re.compile(
        r"\b(?:vendors|makers|brands|suppliers|companies|players|manufacturers|foundries|countries)\b", re.IGNORECASE
    )
    CHANGE: ClassVar[Pattern[str]] = re.compile(
        r"^\s*(?:growth|increase|decrease|decline|gain|drop|loss|rise|jump|change)", re.IGNORECASE
    )
    HIGHEST: ClassVar[float] = 99.0
    TOLERANCE: ClassVar[float] = 100.5

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the reader.

        Args:
            logger (Optional[Logger]): The reader logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.periods = PeriodLabel()

    ############################
    # Internal Helpers Methods #
    ############################

    def _names(self, names: Sequence[str]) -> Optional[Pattern[str]]:
        """Build the pattern of the company names, the longest first.

        Args:
            names (Sequence[str]): The names the firm writes.

        Returns:
            Optional[Pattern[str]]: The pattern, `None` without names.
        """
        escaped = [re.escape(name) for name in sorted(set(names), key=len, reverse=True) if name]
        return re.compile(r"(?<![\w-])(" + "|".join(escaped) + r")(?![\w-])") if escaped else None

    def _period(self, head: str, tail: str, default: Tuple[date, Granularity]) -> Tuple[date, Granularity]:
        """Get the period of a share: stated right after it, else last stated before it, else the release's.

        Args:
            head (str): The sentence before the share.
            tail (str): The sentence after the share.
            default (Tuple[date, Granularity]): The period of the release.

        Returns:
            Tuple[date, Granularity]: The period.
        """
        found = self.PERIOD_AFTER.match(tail)
        if found:
            return self.periods.parse(found.group(1)) or default
        before = [match.group(0) for match in self.PERIOD_ANY.finditer(head)]
        stated = self.periods.parse(before[-1]) if before else None
        return stated or default

    def _consistent(self, shares: List[TableShare]) -> List[TableShare]:
        """Leave out the periods whose shares sum above 100%.

        Args:
            shares (List[TableShare]): The shares read.

        Returns:
            List[TableShare]: The shares of the consistent periods.
        """
        totals: Dict[date, float] = defaultdict(float)
        for _, day, _, value in shares:
            totals[day] += value
        wrong = {day for day, total in totals.items() if total > self.TOLERANCE}
        for day in sorted(wrong):
            self.logger.warning(
                "Release shares of %s sum to %.1f%%: left out as misread.", day.isoformat(), totals[day]
            )
        return [share for share in shares if share[1] not in wrong]

    ############################
    # Publicly Exposed Methods #
    ############################

    def read(self, text: str, names: Sequence[str], default: Tuple[date, Granularity]) -> List[TableShare]:
        """Read the company shares a release text states.

        Args:
            text (str): The release body, as text.
            names (Sequence[str]): The company names the firm writes (its labels in the catalogue).
            default (Tuple[date, Granularity]): The period of the release (from its title).

        Returns:
            List[TableShare]: A share per company and period, the first stated.
        """
        pattern = self._names(names)
        if pattern is None:
            return []
        shares: Dict[Tuple[str, date], TableShare] = {}
        last: Optional[str] = None
        for sentence in self.SENTENCE.split(" ".join(text.split())):
            matches = sorted(
                [*self.SHARE_AFTER.finditer(sentence), *self.SHARE_BEFORE.finditer(sentence)],
                key=lambda match: match.start(),
            )
            for match in matches:
                head, tail = sentence[: match.start()], sentence[match.end() :]
                named = [name.group(1) for name in pattern.finditer(head)]
                if self.GENERIC.search(head) or self.CHANGE.match(tail) or float(match.group(1)) >= self.HIGHEST:
                    continue
                group = not named and self.GROUP.search(sentence) is not None
                company = named[-1] if named else None if group else last
                if company is None:
                    continue
                day, granularity = self._period(head, tail, default)
                key = (company, day)
                if key not in shares:
                    shares[key] = (company, day, granularity, float(match.group(1)))
            mentioned = [name.group(1) for name in pattern.finditer(sentence)]
            last = mentioned[-1] if mentioned else last
        found = self._consistent(list(shares.values()))
        self.logger.debug("%d shares read from the sentences of a release.", len(found))
        return found
