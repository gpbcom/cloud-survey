from __future__ import annotations

# Standard Library Imports.
from typing import Dict, List, Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, model_validator

# First Party Imports.
from models.configuration.llm.enums import LLMTask
from models.configuration.llm.exception import EmptyLLMRoutingError, UnknownLLMProfileError
from models.configuration.llm.model.llm_configuration import LLMConfiguration
from models.configuration.llm.routing.llm_task_route import LLMTaskRoute


class LLMRoutingConfig(BaseModel):
    """Which model answers which task: named tiers (profiles) and the tier of each task.

    Attributes:
        enabled (bool): Whether the routing applies (`False`: every task uses the fallback model).
        default_profile (Optional[str]): The profile of the tasks the routing does not name.
        profiles (Dict[str, LLMConfiguration]): The tiers (e.g. `precise`, `balanced`, `fast`).
        tasks (Dict[LLMTask, LLMTaskRoute]): The tier of each task, with its effort and output overrides.

    Notes:
        Every profile a task or the default names must be declared: a misspelt tier is refused when the file loads,
        not by the first call.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = Field(default=True, description="Whether the routing applies.")
    default_profile: Optional[str] = Field(default=None, description="The profile of the tasks not named.")
    profiles: Dict[str, LLMConfiguration] = Field(default_factory=dict, description="The tiers.")
    tasks: Dict[LLMTask, LLMTaskRoute] = Field(default_factory=dict, description="The tier of each task.")

    @model_validator(mode="after")
    def validate_profiles(self) -> LLMRoutingConfig:
        """Check that an enabled routing declares profiles, and every profile it names.

        Returns:
            LLMRoutingConfig: The routing, unchanged.

        Raises:
            EmptyLLMRoutingError: If an enabled routing declares no profile.
            UnknownLLMProfileError: If a task or the default names an undeclared profile.
        """
        if not self.enabled:
            return self
        if not self.profiles:
            raise EmptyLLMRoutingError()
        problems: List[str] = [
            f"{route.profile!r} (task {task.value})"
            for task, route in self.tasks.items()
            if route.profile not in self.profiles
        ]
        if self.default_profile is not None and self.default_profile not in self.profiles:
            problems.append(f"{self.default_profile!r} (default)")
        if problems:
            raise UnknownLLMProfileError(problems)
        return self

    ############################
    # Publicly Exposed Methods #
    ############################

    def resolve(self, task: LLMTask, fallback: Optional[LLMConfiguration]) -> Optional[LLMConfiguration]:
        """Get the model answering a task.

        Args:
            task (LLMTask): The task.
            fallback (Optional[LLMConfiguration]): The model used without (enabled) routing.

        Returns:
            Optional[LLMConfiguration]: The profile of the task (else the default one) with the task overrides, the
                fallback when the routing is disabled or names no profile for the task.
        """
        if not self.enabled:
            return fallback
        route = self.tasks.get(task)
        name = route.profile if route is not None else self.default_profile
        profile = self.profiles.get(name) if name is not None else None
        if profile is None:
            return fallback
        if route is None:
            return profile
        overrides = {"effort": route.effort, "max_tokens": route.max_tokens}
        return profile.model_copy(update={key: value for key, value in overrides.items() if value is not None})
