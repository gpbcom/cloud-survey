from __future__ import annotations

# Standard Library Imports.
import re
import unicodedata
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Tuple

# First Party Imports.
from models.taxonomy.enums import Language


class LabelNormalizer:
    """Turn the source labels of the providers into de-duplication keys, and tell their language.

    Attributes:
        LATIN_LOOK_ALIKES (ClassVar[Dict[str, str]]): The Latin letters mistaken for Cyrillic ones, by their Cyrillic
            twin (case-folded).
        CONJUNCTIONS (ClassVar[FrozenSet[str]]): The conjunction words dropped from the keys.
        CHINESE_CONJUNCTIONS (ClassVar[str]): The Chinese conjunction characters dropped from the keys.
        KEPT_SUFFIXES (ClassVar[Tuple[str, ...]]): The English endings which are not plurals.
        HAN (ClassVar[re.Pattern[str]]): The Chinese characters.
        CYRILLIC (ClassVar[re.Pattern[str]]): The Cyrillic letters.
        ASCII_WORD (ClassVar[re.Pattern[str]]): A word of Latin letters only.
        logger (Logger): The normalizer logger.

    Notes:
        - The key is the same for the spellings of one label: case, 
          `&` / `and` / `и` / `与`, punctuation, spacing,
          English plurals (`Databases`, `DataBases`, `DATABASE` all give `database`).
        - Latin letters typed inside Cyrillic words
          (a Russian acronym starting with a Latin `C`)
          are read as their Cyrillic twins.
        - The keys are deterministic: they are always computed from
          the text as written, never from a key.
    """

    LATIN_LOOK_ALIKES: ClassVar[Dict[str, str]] = {
        "a": "\u0430",
        "c": "\u0441",
        "e": "\u0435",
        "o": "\u043e",
        "p": "\u0440",
        "x": "\u0445",
        "y": "\u0443",
        "k": "\u043a",
        "m": "\u043c",
        "t": "\u0442",
    }
    CONJUNCTIONS: ClassVar[FrozenSet[str]] = frozenset({"and", "&", "+", "и"})
    CHINESE_CONJUNCTIONS: ClassVar[str] = "与和及、"
    KEPT_SUFFIXES: ClassVar[Tuple[str, ...]] = ("ss", "us", "is", "as")
    HAN: ClassVar[re.Pattern[str]] = re.compile(r"[㐀-䶿一-鿿]")
    CYRILLIC: ClassVar[re.Pattern[str]] = re.compile(r"[Ѐ-ӿ]")
    ASCII_WORD: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z]+$")

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the normalizer.

        Args:
            logger (Optional[Logger]): The normalizer logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _separate(self, text: str) -> str:
        """Turn the punctuation and symbols into spaces, keeping `+` and `#` attached to a word (C++, C#).

        Args:
            text (str): The case-folded text.

        Returns:
            str: The text with separators as spaces.
        """
        characters: List[str] = []
        for character in text:
            previous = characters[-1] if characters else " "
            attached = character in "+#" and (previous.isalnum() or previous in "+#")
            if unicodedata.category(character)[0] in "PS" and not attached:
                characters.append(" ")
            else:
                characters.append(character)
        return "".join(characters)

    def _token(self, token: str) -> str:
        """Normalize a word: Latin look-alikes in Cyrillic words, Chinese conjunctions, English plurals.

        Args:
            token (str): The case-folded word.

        Returns:
            str: The normalized word, empty when nothing is left.
        """
        if self.CYRILLIC.search(token):
            token = "".join(self.LATIN_LOOK_ALIKES.get(character, character) for character in token)
        if self.HAN.search(token):
            token = "".join(character for character in token if character not in self.CHINESE_CONJUNCTIONS)
        if self.ASCII_WORD.match(token) and len(token) > 3:
            if token.endswith("ies"):
                return f"{token[:-3]}y"
            if token.endswith("s") and not token.endswith(self.KEPT_SUFFIXES):
                return token[:-1]
        return token

    ############################
    # Publicly Exposed Methods #
    ############################

    def key(self, text: str) -> str:
        """Get the de-duplication key of a label.

        Args:
            text (str): The label, as written by a provider.

        Returns:
            str: Its key, e.g. `backuprecovery` for `Backup & Recovery`, empty for a label of punctuation only.
        """
        folded = unicodedata.normalize("NFKC", text).casefold()
        tokens = [self._token(token) for token in self._separate(folded).split() if token not in self.CONJUNCTIONS]
        return "".join(token for token in tokens if token)

    def language(self, text: str) -> Language:
        """Tell the language of a label from its script.

        Args:
            text (str): The label.

        Returns:
            Language: Chinese for Han characters, else Russian for Cyrillic letters, else English.
        """
        if self.HAN.search(text):
            return Language.CHINESE
        if self.CYRILLIC.search(text):
            return Language.RUSSIAN
        return Language.ENGLISH
