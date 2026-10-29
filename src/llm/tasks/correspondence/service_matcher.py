from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple, Type

# Third Party Imports.
import anthropic
import openai
from langchain_core.exceptions import LangChainException
from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import ValidationError

# First Party Imports.
from llm.chat_model_factory import ChatModelFactory
from llm.exception import LLMResponseError
from llm.tasks.correspondence.correspondence_prompt import CorrespondencePrompt
from llm.usage_meter import UsageMeter
from models.cloud.enums import CloudProvider
from models.configuration.llm.enums import LLMTask
from models.configuration.llm.llm_settings import LLMSettings
from models.configuration.llm.model.llm_configuration import LLMConfiguration
from models.correspondence.llm.concept_batch import ConceptBatch
from models.taxonomy.nodes.taxonomy import Taxonomy
from storage.storage import Storage


class ServiceMatcher:
    """Group the equivalent catalogue services of the providers into service concepts, with the language model.

    Attributes:
        TASK (ClassVar[LLMTask]): The routing task of the calls.
        BATCH_LIMIT (ClassVar[int]): The largest number of services sent per call.
        CALL_ERRORS (ClassVar[Tuple[Type[Exception], ...]]): The errors of a call which skip its category (logged).
        storage (Storage): The open storage.
        settings (LLMSettings): The language model settings.
        factory (ChatModelFactory): The builder of the chat models.
        prompt (CorrespondencePrompt): The writer of the prompts.
        meter (UsageMeter): The pricer of the calls, keeping them under the budget.
        logger (Logger): The matcher logger.

    Notes:
        - The services are matched category by category (the taxonomy categories holding services of two providers
          at least): each call sends the services waiting to be matched with the concepts already found, so that a
          new service joins the concepts of its category.
        - A category is matched by one run at a time (an advisory lock): a run skips a category another one holds.
        - A failed call (or a service the answer forgets) is tried again by a later run, three times at most.
        - Nothing is sent without a configured model: the run then matches nothing.
    """

    TASK: ClassVar[LLMTask] = LLMTask.SERVICE_CORRESPONDENCE
    BATCH_LIMIT: ClassVar[int] = 60
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
        prompt: Optional[CorrespondencePrompt] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Initialize the matcher.

        Args:
            storage (Storage): The open storage.
            settings (LLMSettings): The language model settings.
            factory (Optional[ChatModelFactory]): The builder of the chat models.
            prompt (Optional[CorrespondencePrompt]): The writer of the prompts, of the project prompts by default.
            logger (Optional[Logger]): The matcher logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.storage = storage
        self.settings = settings
        self.factory = factory if factory else ChatModelFactory(self.logger)
        self.prompt = prompt if prompt else CorrespondencePrompt(logger=self.logger)
        self.meter = UsageMeter(settings.llm_budget, self.logger)
        self.logger.debug("Service matcher ready: %d services per call at most.", self.BATCH_LIMIT)

    ############################
    # Internal Helpers Methods #
    ############################

    async def _call(self, cfg: LLMConfiguration, messages: List[BaseMessage]) -> ConceptBatch:
        """Send a category, record the usage and read the answer.

        Args:
            cfg (LLMConfiguration): The model.
            messages (List[BaseMessage]): The system prompt and the category.

        Returns:
            ConceptBatch: The answer.

        Raises:
            LLMResponseError: If the answer is not of the expected shape.
        """
        result = await self.factory.structured(cfg, ConceptBatch).ainvoke(messages)
        raw = result.get("raw") if isinstance(result, dict) else None
        usage = getattr(raw, "usage_metadata", None)
        currency = self.settings.llm_budget.currency
        cost, tokens = self.meter.cost(cfg, usage), self.meter.tokens(usage)
        await self.storage.llm_usage.record(self.TASK.value, cfg.provider.value, cfg.model_name, tokens, cost, currency)
        parsed = result.get("parsed") if isinstance(result, dict) else None
        if not isinstance(parsed, ConceptBatch):
            error = result.get("parsing_error") if isinstance(result, dict) else None
            self.logger.error("The service correspondence answer cannot be read: %s", error)
            raise LLMResponseError(self.TASK.value, f"unexpected answer ({error})")
        return parsed

    async def _batch(self, cfg: LLMConfiguration, system: BaseMessage, taxonomy: Taxonomy, slug: str) -> Optional[int]:
        """Match the next services waiting in a category.

        Args:
            cfg (LLMConfiguration): The model.
            system (BaseMessage): The system prompt.
            taxonomy (Taxonomy): The stored taxonomy.
            slug (str): The category.

        Returns:
            Optional[int]: The number of services filed under concepts, `None` when no service waits any more or the
                call failed (the category is left for a later run).
        """
        repository = self.storage.correspondences
        self.meter.check(await self.storage.llm_usage.spent(self.settings.llm_budget.currency))
        bucket = await repository.bucket(slug, self.BATCH_LIMIT)
        if not bucket.pending:
            return None
        sent = [service.product_id for service in bucket.pending]
        message = HumanMessage(content=self.prompt.batch(taxonomy, slug, bucket.concepts, bucket.pending))
        try:
            answer = await self._call(cfg, [system, message])
        except self.CALL_ERRORS as e:
            self.logger.warning("The %d services of %s are not matched: %s", len(sent), slug, e)
            await repository.release(slug, sent, str(e))
            return None
        answered = sorted({member.id for concept in answer.concepts for member in concept.members} & set(sent))
        added = await repository.apply_answer(slug, answer.concepts, answered)
        missing = sorted(set(sent) - set(answered))
        if missing:
            await repository.release(slug, missing, "no answer for the service")
        self.logger.info(
            "%s: %d of %d services matched, %d filed under concepts.", slug, len(answered), len(sent), added
        )
        return added

    async def _match(
        self, cfg: LLMConfiguration, system: BaseMessage, taxonomy: Taxonomy, slug: str, calls: int
    ) -> Tuple[int, int]:
        """Match the services waiting in a category, under its lock.

        Args:
            cfg (LLMConfiguration): The model.
            system (BaseMessage): The system prompt.
            taxonomy (Taxonomy): The stored taxonomy.
            slug (str): The category.
            calls (int): The largest number of calls sent.

        Returns:
            Tuple[int, int]: The number of services filed under concepts, then of calls sent.
        """
        repository = self.storage.correspondences
        added, sent = 0, 0
        async with self.storage.database.connect() as connection:
            if not await repository.lock(connection, slug):
                self.logger.info("The category %s is matched by another run: skipped.", slug)
                return 0, 0
            try:
                while sent < calls:
                    done = await self._batch(cfg, system, taxonomy, slug)
                    sent += 1
                    if done is None:
                        break
                    added += done
            finally:
                await repository.unlock(connection, slug)
        return added, sent

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_configured(self) -> bool:
        """Tell whether a model matches the services.

        Returns:
            bool: Whether the task has a model with its API key.
        """
        return self.settings.is_configured(self.TASK)

    async def run(self, provider: Optional[CloudProvider] = None, limit: Optional[int] = None) -> int:
        """Match the services waiting in every category (or in the categories of a provider's waiting services).

        Args:
            provider (Optional[CloudProvider]): Only the categories holding waiting services of this provider (e.g.
                the one just crawled), every category when `None`.
            limit (Optional[int]): The largest number of calls sent, no limit when `None`.

        Returns:
            int: The number of services filed under concepts.

        Raises:
            LLMBudgetExceededError: If the budget is spent (the services matched so far are kept).
        """
        cfg = self.settings.configuration(self.TASK)
        if cfg is None:
            self.logger.info("No language model matches the services: their correspondences wait.")
            return 0
        taxonomy = await self.storage.taxonomy.list()
        system = self.factory.system_message(cfg, self.prompt.system())
        remaining = limit if limit is not None else 1_000_000
        added = 0
        for slug in await self.storage.correspondences.pending_buckets(provider):
            if remaining <= 0:
                break
            done, calls = await self._match(cfg, system, taxonomy, slug, remaining)
            added, remaining = added + done, remaining - calls
        self.logger.info("Service matching over: %d services filed under concepts.", added)
        return added
