from __future__ import annotations

# Standard Library Imports.
from typing import List


class LLMConfigurationModelError(ValueError):
    """Base class for every invalid language model configuration."""


class UnknownLLMProfileError(LLMConfigurationModelError):
    """Raised when the routing names a profile it does not declare.

    Attributes:
        problems (List[str]): The undeclared profiles and where they are named.
    """

    def __init__(self, problems: List[str]) -> None:
        """Initialize the error.

        Args:
            problems (List[str]): The undeclared profiles and where they are named.
        """
        self.problems = problems
        super().__init__(f"Unknown LLM profiles: {'; '.join(problems)}.")


class EmptyLLMRoutingError(LLMConfigurationModelError):
    """Raised when an enabled routing declares no profile."""

    def __init__(self) -> None:
        """Initialize the error."""
        super().__init__("An enabled LLM routing must declare at least one profile.")
