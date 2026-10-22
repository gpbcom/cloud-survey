from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class MemberRole(StrEnum):
    """Enums representing how a service matches the concept it belongs to.

    Attributes:
        EQUIVALENT (str): The service does what the concept stands for.
        PARTIAL (str): The service covers part of the concept only (or more than it).
    """

    EQUIVALENT = "equivalent"
    PARTIAL = "partial"


@unique
class ConceptSource(StrEnum):
    """Enums representing who set a service concept or one of its members.

    Attributes:
        LLM (str): The language model.
        USER (str): A person, in the Correspondences tab: never changed by the language model.
    """

    LLM = "llm"
    USER = "user"


@unique
class CardinalityClass(StrEnum):
    """Enums representing how many services of two providers correspond to each other in a concept.

    Attributes:
        ONE_TO_ONE (str): One service on each side.
        TWO_TO_ONE (str): Two services on one side (one or two on the other).
        THREE_TO_ONE (str): Three services on one side.
        MANY_TO_ONE (str): Four services or more on one side.
        MISSING (str): One of the providers has no service of the concept.
    """

    ONE_TO_ONE = "1:1"
    TWO_TO_ONE = "2:1"
    THREE_TO_ONE = "3:1"
    MANY_TO_ONE = "n:1"
    MISSING = "missing"


@unique
class CoverageFilter(StrEnum):
    """Enums representing which concepts are shown, by the provider columns holding one of their services.

    Attributes:
        ALL (str): Every concept with a service in one of the columns at least.
        COMPLETE (str): The concepts with a service in every column.
        GAPS (str): The concepts with a service in two columns at least, missing in one at least.
        UNIQUE (str): The concepts with a service in one column only.
    """

    ALL = "all"
    COMPLETE = "complete"
    GAPS = "gaps"
    UNIQUE = "unique"


@unique
class MatchStrength(StrEnum):
    """Enums representing which members of the concepts are shown.

    Attributes:
        EQUIVALENT (str): The equivalent services only.
        ANY (str): The equivalent and the partial services.
    """

    EQUIVALENT = "equivalent"
    ANY = "any"


@unique
class ViewMode(StrEnum):
    """Enums representing what the rows of the correspondence diagram stand for.

    Attributes:
        CONCEPTS (str): The service concepts the AI matched (equivalent services).
        CATEGORIES (str): The taxonomy categories: the services of each provider filed under the same category,
            without the AI (a coarser alignment, read-only).
    """

    CONCEPTS = "concepts"
    CATEGORIES = "categories"
