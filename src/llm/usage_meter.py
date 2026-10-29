from __future__ import annotations

# Standard Library Imports.
from decimal import Decimal
from logging import Logger, getLogger
from typing import ClassVar, Mapping, Optional, Tuple, Union

# First Party Imports.
from llm.exception import LLMBudgetExceededError
from models.configuration.llm.model.llm_budget_config import LLMBudgetConfig
from models.configuration.llm.model.llm_configuration import LLMConfiguration

type UsageValue = Optional[Union[int, Mapping[str, int]]]


class UsageMeter:
    """Price the language model calls and keep them under the budget ceiling.

    Attributes:
        MILLION (ClassVar[Decimal]): The unit of the rates.
        CACHE_WRITE_FACTOR (ClassVar[Decimal]): The price of a cache write relative to an input token (5-minute cache).
        budget (LLMBudgetConfig): The budget.
        logger (Logger): The meter logger.

    Notes:
        The LangChain usage counts every input token, 
        the cached ones included (`input_token_details` tells the cache
        reads and writes): the uncached tokens are priced at the 
        input rate, the cache reads at the cache rate and the
        cache writes at 1.25 times the input rate.
    """

    MILLION: ClassVar[Decimal] = Decimal(1000000)
    CACHE_WRITE_FACTOR: ClassVar[Decimal] = Decimal("1.25")

    def __init__(self, budget: LLMBudgetConfig, logger: Optional[Logger] = None) -> None:  # noqa: E501
        """Initialize the meter.

        Args:
            budget (LLMBudgetConfig): The budget.
            logger (Optional[Logger]): The meter logger.
        """
        self.budget = budget
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def tokens(self, usage: Optional[Mapping[str, UsageValue]]) -> Tuple[int, int, int, int]:  # noqa: E501
        """Read the token counts of a call.

        Args:
            usage (Optional[Mapping[str, UsageValue]]): The `usage_metadata` of the answer, `None` when missing.

        Returns:
            Tuple[int, int, int, int]: The uncached input tokens, the output tokens, the cache reads and the cache
                writes.
        """
        if not usage:
            self.logger.warning("The answer carries no token usage: the call is recorded at no cost.")
            return 0, 0, 0, 0
        details = usage.get("input_token_details")
        cache_read = int(details.get("cache_read", 0) or 0) if isinstance(details, Mapping) else 0  # noqa: E501  
        cache_write = int(details.get("cache_creation", 0) or 0) if isinstance(details, Mapping) else 0  # noqa: E501
        total_input = usage.get("input_tokens")
        output = usage.get("output_tokens")
        uncached = max(int(total_input or 0) - cache_read - cache_write, 0) if isinstance(total_input, int) else 0  # noqa: E501
        output_tokens = int(output or 0) if isinstance(output, int) else 0
        self.logger.debug(
            "Tokens used: %d uncached input, %d output, %d cache reads, %d cache writes.",
            uncached,
            output_tokens,
            cache_read,
            cache_write,
        )
        return uncached, output_tokens, cache_read, cache_write

    def cost(self, cfg: LLMConfiguration, usage: Optional[Mapping[str, UsageValue]]) -> Decimal:  # noqa: E501
        """Price a call.

        Args:
            cfg (LLMConfiguration): The model of the call.
            usage (Optional[Mapping[str, UsageValue]]): The `usage_metadata` of the answer.

        Returns:
            Decimal: The cost of the call, in the currency of the rates.
        """
        uncached, output, cache_read, cache_write = self.tokens(usage)
        cost = (
            Decimal(uncached) * cfg.input_rate_per_million
            + Decimal(cache_write) * cfg.input_rate_per_million * self.CACHE_WRITE_FACTOR # noqa: E501
            + Decimal(cache_read) * cfg.cache_read_rate()
            + Decimal(output) * cfg.output_rate_per_million
        ) / self.MILLION
        self.logger.debug("Call of %s priced %.6f (%d in, %d out).", cfg.model_name, cost, uncached, output)  # noqa: E501
        return cost

    def check(self, spent: Decimal) -> None:
        """Refuse a new call once the budget is spent (or warn, when it is not enforced).

        Args:
            spent (Decimal): What the recorded calls cost.

        Raises:
            LLMBudgetExceededError: If the ceiling is reached and enforced.
        """
        if spent < self.budget.ceiling:
            return
        if self.budget.enforce:
            self.logger.error(
                "The language model budget is spent: %.4f of %.2f %s.", spent, self.budget.ceiling, self.budget.currency  # noqa: E501
            )
            raise LLMBudgetExceededError(spent, self.budget.ceiling, self.budget.currency)
        self.logger.warning(
            "The language model budget is exceeded (not enforced): %.4f of %.2f.", spent, self.budget.ceiling
        )
