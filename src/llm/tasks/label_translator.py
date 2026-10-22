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
from llm.tasks.taxonomy_prompt import TaxonomyPrompt
from llm.usage_meter import UsageMeter
from models.configuration.llm.enums import LLMTask
from models.configuration.llm.llm_settings import LLMSettings
from models.configuration.llm.model.llm_configuration import LLMConfiguration
from models.taxonomy.llm.translation_batch import TranslationBatch
from models.taxonomy.nodes.taxonomy import Taxonomy
from storage.storage import Storage


class LabelTranslator:
    """Translate the pending source labels with the language model, and link them to the taxonomy.

    Attributes:
        TASK (ClassVar[LLMTask]): The routing task of the calls.
        CALL_ERRORS (ClassVar[Tuple[Type[Exception], ...]]): The errors of a call which skip its batch (logged).
        storage (Storage): The open storage.
        settings (LLMSettings): The language model settings.
        factory (ChatModelFactory): The builder of the chat models.
        prompt (TaxonomyPrompt): The writer of the prompts.
        meter (UsageMeter): The pricer of the calls, keeping them under the budget.
        logger (Logger): The translator logger.

    Notes:
        - The labels are claimed by batches (`batch_size` of the settings): concurrent runs never translate the same
          label, and a batch whose call fails is released with its error, retried by a later run (three attempts).
        - The answers never overwrite what a person set, and the items of the translated labels (and of their aliases)
          are categorized again.
        - Nothing is sent without a configured model: the run then translates nothing.
    """

    TASK: ClassVar[LLMTask] = LLMTask.LABEL_TRANSLATION
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
        """Initialize the translator.

        Args:
            storage (Storage): The open storage.
            settings (LLMSettings): The language model settings.
            factory (Optional[ChatModelFactory]): The builder of the chat models.
            prompt (Optional[TaxonomyPrompt]): The writer of the prompts, of the project prompts by default.
            logger (Optional[Logger]): The translator logger.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.storage = storage
        self.settings = settings
        self.factory = factory if factory else ChatModelFactory(self.logger)
        self.prompt = prompt if prompt else TaxonomyPrompt(logger=self.logger)
        self.meter = UsageMeter(settings.llm_budget, self.logger)

    ############################
    # Internal Helpers Methods #
    ############################

    async def _call(self, cfg: LLMConfiguration, messages: List[BaseMessage]) -> TranslationBatch:
        """Send a batch, record its usage and read the answer.

        Args:
            cfg (LLMConfiguration): The model.
            messages (List[BaseMessage]): The system prompt and the batch.

        Returns:
            TranslationBatch: The answer.

        Raises:
            LLMResponseError: If the answer is not of the expected shape.
        """
        result = await self.factory.structured(cfg, TranslationBatch).ainvoke(messages)
        raw = result.get("raw") if isinstance(result, dict) else None
        usage = getattr(raw, "usage_metadata", None)
        budget = self.settings.llm_budget
        cost = self.meter.cost(cfg, usage)
        tokens = self.meter.tokens(usage)
        await self.storage.llm_usage.record(
            self.TASK.value, cfg.provider.value, cfg.model_name, tokens, cost, budget.currency
        )
        parsed = result.get("parsed") if isinstance(result, dict) else None
        if not isinstance(parsed, TranslationBatch):
            error = result.get("parsing_error") if isinstance(result, dict) else None
            self.logger.error("The label translation answer cannot be read: %s", error)
            raise LLMResponseError(self.TASK.value, f"unexpected answer ({error})")
        return parsed

    async def _batch(self, cfg: LLMConfiguration, taxonomy: Taxonomy, system: BaseMessage) -> Optional[int]:
        """Claim, translate and write a batch of pending labels.

        Args:
            cfg (LLMConfiguration): The model.
            taxonomy (Taxonomy): The stored taxonomy.
            system (BaseMessage): The system prompt.

        Returns:
            Optional[int]: The number of labels translated, `None` when no label is pending any more.
        """
        self.meter.check(await self.storage.llm_usage.spent(self.settings.llm_budget.currency))
        labels = await self.storage.labels.claim_pending(self.settings.batch_size)
        if not labels:
            return None
        ids = [label.id for label in labels]
        seen = await self.storage.labels.seen_at(ids)
        try:
            answer = await self._call(cfg, [system, HumanMessage(content=self.prompt.labels(labels, seen))])
        except self.CALL_ERRORS as e:
            self.logger.warning("A batch of %d labels is not translated: %s", len(ids), e)
            await self.storage.labels.release(ids, str(e))
            return 0
        answered = [translation for translation in answer.labels if translation.id in set(ids)]
        slugs = {node.slug for node in taxonomy.nodes if not node.hidden}
        affected = await self.storage.labels.apply_translations(answered, slugs)
        missing = sorted(set(ids) - {translation.id for translation in answered})
        if missing:
            await self.storage.labels.release(missing, "no answer for the label")
        await self.storage.recategorize(label_ids=affected)
        self.logger.info("%d of %d labels translated.", len(answered), len(ids))
        return len(answered)

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_configured(self) -> bool:
        """Tell whether a model translates the labels.

        Returns:
            bool: Whether the task has a model with its API key.
        """
        return self.settings.is_configured(self.TASK)

    async def run(self, limit: Optional[int] = None) -> int:
        """Translate the pending labels, batch after batch.

        Args:
            limit (Optional[int]): The largest number of batches sent, every pending label when `None`.

        Returns:
            int: The number of labels translated.

        Raises:
            LLMBudgetExceededError: If the budget is spent (the labels translated so far are kept).
        """
        cfg = self.settings.configuration(self.TASK)
        if cfg is None:
            self.logger.info("No language model translates the labels: they wait in the Categories manager.")
            return 0
        taxonomy = await self.storage.taxonomy.read()
        system = self.factory.system_message(cfg, self.prompt.system(self.TASK, taxonomy))
        translated, batches = 0, 0
        while limit is None or batches < limit:
            done = await self._batch(cfg, taxonomy, system)
            if done is None:
                break
            translated += done
            batches += 1
        self.logger.info("Label translation over: %d labels translated in %d batches.", translated, batches)
        return translated
