from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field

# First Party Imports.
from models.configuration.llm.enums import LLMTask
from models.configuration.llm.model.llm_budget_config import LLMBudgetConfig
from models.configuration.llm.model.llm_configuration import LLMConfiguration
from models.configuration.llm.routing.llm_routing_config import LLMRoutingConfig


class LLMSettings(BaseModel):
    """The language model settings of the crawler (`conf/llm.yaml`): the fallback model, the routing, the budget.

    Attributes:
        llm (Optional[LLMConfiguration]): The model used without (enabled) routing, `None` for none.
        llm_routing (Optional[LLMRoutingConfig]): The model of each task.
        llm_budget (LLMBudgetConfig): What the calls may spend in total.
        batch_size (int): The number of labels or items sent per call.
        after_crawl (bool): Whether the pending labels and the unclassified items of a crawled provider are sent to the
            model once its crawl is over.

    Notes:
        Without a model whose API key is set, nothing is sent: the new labels wait in the Categories manager (pending)
        and the items nothing else categorized stay unclassified.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    llm: Optional[LLMConfiguration] = Field(default=None, description="The fallback model.")
    llm_routing: Optional[LLMRoutingConfig] = Field(default=None, description="The model of each task.")
    llm_budget: LLMBudgetConfig = Field(default_factory=LLMBudgetConfig, description="The spending ceiling.")
    batch_size: int = Field(default=50, ge=1, le=200, description="The labels or items sent per call.")
    after_crawl: bool = Field(default=True, description="Whether a crawl ends with the model tasks.")

    ############################
    # Publicly Exposed Methods #
    ############################

    def configuration(self, task: LLMTask) -> Optional[LLMConfiguration]:
        """Get the model answering a task, when it can be called.

        Args:
            task (LLMTask): The task.

        Returns:
            Optional[LLMConfiguration]: The routed model (else the fallback one), `None` when none is configured or its
                API key is unset.
        """
        model = self.llm_routing.resolve(task, self.llm) if self.llm_routing is not None else self.llm
        return model if model is not None and model.is_configured() else None

    def is_configured(self, task: LLMTask) -> bool:
        """Tell whether a task can be sent to a model.

        Args:
            task (LLMTask): The task.

        Returns:
            bool: Whether a model with its API key answers it.
        """
        return self.configuration(task) is not None
