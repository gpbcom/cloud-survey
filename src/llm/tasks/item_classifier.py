from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple, Type

# Third Party Imports.
import anthropic
import openai
from langchain_core.exceptions import LangChainException
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import ValidationError

# First Party Imports.
from llm.chat_model_factory import ChatModelFactory
from llm.exception import LLMResponseError
from llm.tasks.taxonomy_prompt import TaxonomyPrompt
from llm.usage_meter import UsageMeter
from models.cloud.categorized_item import CategorizedItem
from models.cloud.enums import CloudProvider
from models.configuration.llm.enums import LLMTask
from models.configuration.llm.llm_settings import LLMSettings
from models.configuration.llm.model.llm_configuration import LLMConfiguration
from models.storage.pages.stored_item import StoredItem
from models.taxonomy.llm.categorization_batch import CategorizationBatch
from models.taxonomy.nodes.taxonomy import Taxonomy
from storage.repositories.item_repository import ItemRepository
from storage.storage import Storage


class ItemClassifier:
    """File the items nothing else categorized (`other`) under taxonomy categories, with the language model.

    Attributes:
        TASK (ClassVar[LLMTask]): The routing task of the calls.
        CALL_ERRORS (ClassVar[Tuple[Type[Exception], ...]]): The errors of a call which skip its batch (logged).
        storage (Storage): The open storage.
        settings (LLMSettings): The language model settings.
        factory (ChatModelFactory): The builder of the chat models.
        prompt (TaxonomyPrompt): The writer of the prompts.
        meter (UsageMeter): The pricer of the calls, keeping them under the budget.
        logger (Logger): The classifier logger.

    Notes:
        - This is the fifth rung of the categorization:
         the answers are kept until the content of an item changes,
          and never replace categories a person set.
        - Only categories which exist are kept
          (never `other`, never a domain): an item the model cannot file stays
          unclassified, for the Categories manager.
    """

    TASK: ClassVar[LLMTask] = LLMTask.ITEM_CLASSIFICATION
    CALL_ERRORS: ClassVar[Tuple[Type[Exception], ...]] = (
        anthropic.APIError,
        openai.APIError,
        LangChainException,
        ValidationError,
        LLMResponseError,
    )

    def __init__(
        self,
        storage: Storage,
        settings: LLMSettings,
        factory: Optional[ChatModelFactory] = None,
        prompt: Optional[TaxonomyPrompt] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the classifier.

        Args:
            storage (Storage): The open storage.
            settings (LLMSettings): The language model settings.
            factory (Optional[ChatModelFactory]): The builder of the chat models.
            prompt (Optional[TaxonomyPrompt]): The writer of the prompts, of the project prompts by default.
            logger (Optional[Logger]): The classifier logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.storage = storage
        self.settings = settings
        self.factory = factory if factory else ChatModelFactory(self.logger)
        self.prompt = prompt if prompt else TaxonomyPrompt(logger=self.logger)
        self.meter = UsageMeter(settings.llm_budget, self.logger)
        self.logger.debug("Item classifier ready: %d items per call.", settings.batch_size)

    ############################
    # Internal Helpers Methods #
    ############################

    async def _call(self, cfg: LLMConfiguration, messages: List[BaseMessage]) -> CategorizationBatch:  
        """Send a batch, record its usage and read the answer.

        Args:
            cfg (LLMConfiguration): The model.
            messages (List[BaseMessage]): The system prompt and the batch.

        Returns:
            CategorizationBatch: The answer.

        Raises:
            LLMResponseError: If the answer is not of the expected shape.
        """
        result = await self.factory.structured(cfg, CategorizationBatch).ainvoke(messages)
        raw = result.get("raw") if isinstance(result, dict) else None
        usage = getattr(raw, "usage_metadata", None)
        currency = self.settings.llm_budget.currency
        cost, tokens = self.meter.cost(cfg, usage), self.meter.tokens(usage)
        await self.storage.llm_usage.record(self.TASK.value, cfg.provider.value, cfg.model_name, tokens, cost, currency)
        parsed = result.get("parsed") if isinstance(result, dict) else None
        if not isinstance(parsed, CategorizationBatch):
            error = result.get("parsing_error") if isinstance(result, dict) else None
            self.logger.error("The item classification answer cannot be read: %s", error)
            raise LLMResponseError(self.TASK.value, f"unexpected answer ({error})")
        return parsed

    def _categories(self, answer: CategorizationBatch, taxonomy: Taxonomy) -> Dict[int, Tuple[List[str], List[str]]]:  # noqa: E501
        """Keep the known categories of each answer, with their domains.

        Args:
            answer (CategorizationBatch): The answer.
            taxonomy (Taxonomy): The stored taxonomy.

        Returns:
            Dict[int, Tuple[List[str], List[str]]]: The categories and domains of each item filed somewhere.
        """
        kept: Dict[int, Tuple[List[str], List[str]]] = {}
        for item in answer.items:
            slugs = taxonomy.ordered(slug for slug in item.slugs if taxonomy.is_category(slug) and slug != "other")
            if slugs:
                domains = taxonomy.ordered(domain for slug in slugs if (domain := taxonomy.domain_of(slug)))
                kept[item.id] = (slugs, domains)
        if len(kept) < len(answer.items):
            self.logger.debug(
                "%d of the %d answered items got no known category and stay unclassified.",
                len(answer.items) - len(kept),
                len(answer.items),
            )
        return kept

    async def _classify[T: CategorizedItem](
        self,
        cfg: LLMConfiguration,
        repository: ItemRepository[T],
        taxonomy: Taxonomy,
        system: BaseMessage,
        provider: Optional[CloudProvider],
        limit: Optional[int],
    ) -> int:
        """Classify the unclassified items of a repository, batch after batch.

        Args:
            cfg (LLMConfiguration): The model.
            repository (ItemRepository[T]): The products or the software.
            taxonomy (Taxonomy): The stored taxonomy.
            system (BaseMessage): The system prompt.
            provider (Optional[CloudProvider]): Only the items of a provider, every provider when `None`.
            limit (Optional[int]): The largest number of batches sent.

        Returns:
            int: The number of items filed under categories.
        """
        after, batches, changed = 0, 0, 0
        while limit is None or batches < limit:
            self.meter.check(await self.storage.llm_usage.spent(self.settings.llm_budget.currency))
            items: List[StoredItem[T]] = await repository.unclassified_batch(self.settings.batch_size, after, provider)
            if not items:
                break
            after, batches = items[-1].id, batches + 1
            batch = [(stored.id, stored.provider.value, stored.item) for stored in items]
            try:
                answer = await self._call(cfg, [system, HumanMessage(content=self.prompt.items(batch))])
            except self.CALL_ERRORS as e:
                self.logger.warning("A batch of %d %s items is not classified: %s", len(items), repository.kind, e)
                continue
            changed += await repository.apply_llm_categories(self._categories(answer, taxonomy))
        return changed

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_configured(self) -> bool:
        """Tell whether a model classifies the items.

        Returns:
            bool: Whether the task has a model with its API key.
        """
        return self.settings.is_configured(self.TASK)

    async def run(self, provider: Optional[CloudProvider] = None, limit: Optional[int] = None) -> int:
        """Classify the unclassified products and software.

        Args:
            provider (Optional[CloudProvider]): Only the items of a provider (e.g. the one just crawled), every
                provider when `None`.
            limit (Optional[int]): The largest number of batches sent per kind of items, all of them when `None`.

        Returns:
            int: The number of items filed under categories.

        Raises:
            LLMBudgetExceededError: If the budget is spent (the items classified so far are kept).
        """
        cfg = self.settings.configuration(self.TASK)
        if cfg is None:
            self.logger.info("No language model classifies the items: they stay unclassified.")
            return 0
        taxonomy = await self.storage.taxonomy.list()
        system = self.factory.system_message(cfg, self.prompt.system(self.TASK, taxonomy))
        changed = await self._classify(cfg, self.storage.catalogues, taxonomy, system, provider, limit)
        changed += await self._classify(cfg, self.storage.marketplaces, taxonomy, system, provider, limit)
        self.logger.info("Item classification over: %d items categorized by the language model.", changed)
        return changed
