from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique


@unique
class LLMProvider(StrEnum):
    """Enums representing the providers of the language models.

    Attributes:
        ANTHROPIC (str): Anthropic (Claude models).
        OPENAI (str): OpenAI.
    """

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


@unique
class LLMTask(StrEnum):
    """Enums representing what the language model is asked for (each task routed to its own tier).

    Attributes:
        LABEL_TRANSLATION (str): Translate the source labels into English and link them to the taxonomy.
        ITEM_CLASSIFICATION (str): File the items nothing else categorized under taxonomy categories.
        SERVICE_CORRESPONDENCE (str): Group the equivalent catalogue services of the providers into service concepts.
    """

    LABEL_TRANSLATION = "label_translation"
    ITEM_CLASSIFICATION = "item_classification"
    SERVICE_CORRESPONDENCE = "service_correspondence"


@unique
class LLMEffort(StrEnum):
    """Enums representing how much a model thinks before answering (Anthropic `output_config.effort`).

    Attributes:
        LOW (str): The least thinking, for simple high-volume tasks.
        MEDIUM (str): A balance of quality and cost.
        HIGH (str): Thorough.
        XHIGH (str): More thorough (Anthropic only, clamped to `high` on OpenAI).
        MAX (str): The most thorough (Anthropic only, clamped to `high` on OpenAI).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"
