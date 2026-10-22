from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class Language(StrEnum):
    """Enums representing the languages of the source labels of the providers.

    Attributes:
        ENGLISH (str): English, and every other Latin-script language.
        RUSSIAN (str): Russian (Cyrillic script).
        CHINESE (str): Chinese (Han characters).
    """

    ENGLISH = "en"
    RUSSIAN = "ru"
    CHINESE = "zh"


@unique
class LabelStatus(StrEnum):
    """Enums representing where a source label stands in its review.

    Attributes:
        PENDING (str): Not translated yet: waits for the language model or a person.
        TRANSLATED (str): Translated (English as written, or by the language model), not reviewed by a person.
        REVIEWED (str): Checked by a person, or seeded.
        NOISE (str): Not a category (e.g. a "Products" tab or "Other"): ignored when categorizing the items.
    """

    PENDING = "pending"
    TRANSLATED = "translated"
    REVIEWED = "reviewed"
    NOISE = "noise"


@unique
class NameSource(StrEnum):
    """Enums representing where a value of a source label comes from.

    Attributes:
        IDENTITY (str): The label is English: its English name is its text.
        RULE (str): The classification rules.
        SEED (str): The seed files of the project.
        LLM (str): The language model.
        USER (str): A person, in the Categories manager: never overwritten.
    """

    IDENTITY = "identity"
    RULE = "rule"
    SEED = "seed"
    LLM = "llm"
    USER = "user"


@unique
class NodeOrigin(StrEnum):
    """Enums representing where a node of the taxonomy comes from.

    Attributes:
        SEED (str): The taxonomy seed file of the project.
        USER (str): Added by a person in the Categories manager.
    """

    SEED = "seed"
    USER = "user"


@unique
class CategorySource(StrEnum):
    """Enums representing what gave an item its categories.

    Attributes:
        RULES (str): Its source labels, the classification rules or its delivery method: recomputed on demand.
        LLM (str): The language model: kept until the content of the item changes.
        USER (str): A person: never recomputed.
    """

    RULES = "rules"
    LLM = "llm"
    USER = "user"


@unique
class LinkSource(StrEnum):
    """Enums representing what links a source label to a taxonomy node.

    Attributes:
        RULE (str): The classification rules, when the label was first seen: recomputed with the rules.
        SEED (str): The label seed file of the project: synchronized with it.
        LLM (str): The language model, when it translated the label.
        USER (str): A person, in the Categories manager: never overwritten (an exclusion included).
    """

    RULE = "rule"
    SEED = "seed"
    LLM = "llm"
    USER = "user"
