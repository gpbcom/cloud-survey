from __future__ import annotations

# Standard Library Imports.
import re
from logging import Logger, getLogger
from typing import ClassVar, FrozenSet, Optional, Pattern


class CompanyNames:
    """Compare the names of companies as the sources write them: legal forms, punctuation and case left out.

    Attributes:
        LEGAL_FORMS (ClassVar[FrozenSet[str]]): The words of a legal form or a share class, left out of a name.
        PARENTHESES (ClassVar[Pattern[str]]): A parenthesised part of a name (OpenAlex adds the country).
        SEPARATORS (ClassVar[Pattern[str]]): What separates the words of a name.
        logger (Logger): The comparer logger.

    Notes:
        `International Business Machines Corp`, `INTERNATIONAL BUSINESS MACHINES CORP /NY/` and `International
        Business Machines (United States)` share the key `international business machines`: two names match when
        their keys are equal, never when one only contains the other (a homonym often does).
    """

    LEGAL_FORMS: ClassVar[FrozenSet[str]] = frozenset(
        {
            "a", "ab", "ag", "ads", "adr", "as", "asa", "b", "bv", "class", "co", "company", "corp", "corporation",
            "de", "del", "gmbh", "group", "holding", "holdings", "inc", "incorporated", "kk", "llc", "lp", "ltd",
            "limited", "nv", "ny", "oyj", "plc", "sa", "se", "spa", "the",
        }
    )  # fmt: skip
    PARENTHESES: ClassVar[Pattern[str]] = re.compile(r"\([^)]*\)")
    SEPARATORS: ClassVar[Pattern[str]] = re.compile(r"[^0-9a-z]+")

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the comparer.

        Args:
            logger (Optional[Logger]): The comparer logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def key(self, name: str) -> str:
        """Get the key of a name: its words, lower-case, without legal form, punctuation or parenthesised part.

        Args:
            name (str): The name.

        Returns:
            str: Its key, empty when nothing but a legal form is left.
        """
        text = self.PARENTHESES.sub(" ", name.casefold().replace("&", " and "))
        words = [word for word in self.SEPARATORS.split(text) if word and word not in self.LEGAL_FORMS]
        return " ".join(words)

    def match(self, name: str, other: str) -> bool:
        """Tell whether two names name the same company.

        Args:
            name (str): A name.
            other (str): Another name.

        Returns:
            bool: Whether their keys are equal and not empty.
        """
        key = self.key(name)
        matched = bool(key) and key == self.key(other)
        if matched:
            self.logger.debug("The names %r and %r match.", name, other)
        return matched
