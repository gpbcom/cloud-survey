from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple, Type, Union

# Third Party Imports.
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

# First Party Imports.
from llm.exception import UnsupportedLLMProviderError
from models.configuration.llm.enums import LLMEffort, LLMProvider
from models.configuration.llm.model.llm_configuration import LLMConfiguration

type ClientValue = Union[str, int, float, SecretStr, Dict[str, None]]


class ChatModelFactory:
    """Build the LangChain chat models of the language model settings (modelled on `rt_llm.factory`).

    Attributes:
        ADAPTIVE_PREFIXES (ClassVar[Tuple[str, ...]]): The Claude models which take no temperature and take an effort.
        OPENAI_EFFORT_PREFIXES (ClassVar[Tuple[str, ...]]): The OpenAI models which take a reasoning effort.
        OPENAI_EFFORT_CEILING (ClassVar[LLMEffort]): The largest OpenAI reasoning effort (`xhigh` and `max` clamped).
        logger (Logger): The factory logger.

    Notes:
        - The structured answers use `json_schema` (`output_config.format`) on Anthropic: the current Claude models
          refuse the forced tool use LangChain's default method sends. OpenAI keeps function calling.
        - The prompt caching marker (`cache_control`) is set on Anthropic system prompts only: OpenAI caches by
          itself and rejects the field.
        - No tracing callback is attached (no Langfuse in this project): the usage is recorded by `UsageMeter`.
    """

    ADAPTIVE_PREFIXES: ClassVar[Tuple[str, ...]] = (
        "claude-fable-",
        "claude-mythos-",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-haiku-5",
        "claude-opus-4-7",
        "claude-opus-4-8",
    )
    OPENAI_EFFORT_PREFIXES: ClassVar[Tuple[str, ...]] = ("o", "gpt-5")
    OPENAI_EFFORT_CEILING: ClassVar[LLMEffort] = LLMEffort.HIGH

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the factory.

        Args:
            logger (Optional[Logger]): The factory logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _anthropic(self, cfg: LLMConfiguration) -> BaseChatModel:
        """Build a Claude chat model.

        Args:
            cfg (LLMConfiguration): The model settings.

        Returns:
            BaseChatModel: The `ChatAnthropic` model: an effort and no temperature on the current models, a
                temperature (and no effort) on the older ones.
        """
        kwargs: Dict[str, ClientValue] = {"model": cfg.model_name, "max_tokens": cfg.max_tokens}  # noqa: E501
        if cfg.api_key is not None:
            kwargs["api_key"] = cfg.api_key
        if cfg.model_name.startswith(self.ADAPTIVE_PREFIXES):
            if cfg.effort is not None:
                kwargs["effort"] = cfg.effort.value
        else:
            if cfg.effort is not None:
                self.logger.warning("Model %s predates the effort setting: %s is ignored.", cfg.model_name, cfg.effort)
            if cfg.temperature is not None:
                kwargs["temperature"] = cfg.temperature
        return ChatAnthropic(**kwargs)

    def _openai(self, cfg: LLMConfiguration) -> BaseChatModel:
        """Build an OpenAI chat model.

        Args:
            cfg (LLMConfiguration): The model settings.

        Returns:
            BaseChatModel: The `ChatOpenAI` model, without parallel tool calls (some reasoning models reject them).
        """
        kwargs: Dict[str, ClientValue] = {
            "model": cfg.model_name,
            "max_tokens": cfg.max_tokens,
            "disabled_params": {"parallel_tool_calls": None},
        }
        if cfg.api_key is not None:
            kwargs["api_key"] = cfg.api_key
        if cfg.temperature is not None:
            kwargs["temperature"] = cfg.temperature
        if cfg.effort is not None and cfg.model_name.startswith(self.OPENAI_EFFORT_PREFIXES):  # noqa: E501
            effort = cfg.effort if cfg.effort not in (LLMEffort.XHIGH, LLMEffort.MAX) else self.OPENAI_EFFORT_CEILING  # noqa: E501
            kwargs["reasoning_effort"] = effort.value
        elif cfg.effort is not None:
            self.logger.warning("Model %s takes no reasoning effort: %s is ignored.", cfg.model_name, cfg.effort)
        return ChatOpenAI(**kwargs)

    ############################
    # Publicly Exposed Methods #
    ############################

    def make(self, cfg: LLMConfiguration) -> BaseChatModel:
        """Build the chat model of a model settings.

        Args:
            cfg (LLMConfiguration): The model settings.

        Returns:
            BaseChatModel: The chat model.

        Raises:
            UnsupportedLLMProviderError: If no client is built for the provider.
        """
        self.logger.debug("Building the %s model %s.", cfg.provider.value, cfg.model_name)  # noqa: E501
        match cfg.provider:
            case LLMProvider.ANTHROPIC:
                return self._anthropic(cfg)
            case LLMProvider.OPENAI:
                return self._openai(cfg)
            case _:
                self.logger.error("No language model client for the provider %s.", cfg.provider)
                raise UnsupportedLLMProviderError(str(cfg.provider))

    def structured[T: BaseModel](self, cfg: LLMConfiguration, schema: Type[T]) -> Runnable:  # type: ignore[type-arg]
        """Build a chat model answering with a structured output, its raw message (and usage) included.

        Args:
            cfg (LLMConfiguration): The model settings.
            schema (Type[T]): The pydantic model of the answer.

        Returns:
            Runnable: The model, answering `{"raw": AIMessage, "parsed": T, "parsing_error": ...}`.

        Raises:
            UnsupportedLLMProviderError: If no client is built for the provider.
        """
        method = "json_schema" if cfg.provider is LLMProvider.ANTHROPIC else "function_calling"  # noqa: E501
        self.logger.debug("Structured %s answers of %s with %s.", schema.__name__, cfg.model_name, method)
        return self.make(cfg).with_structured_output(schema, method=method, include_raw=True)

    def system_message(self, cfg: LLMConfiguration, text: str) -> SystemMessage:  # noqa: E501
        """Build a system prompt, cached by Anthropic.

        Args:
            cfg (LLMConfiguration): The model settings.
            text (str): The prompt, the same from one call to the next.

        Returns:
            SystemMessage: The prompt, with the `cache_control` marker for Anthropic.
        """
        if cfg.provider is LLMProvider.ANTHROPIC:
            return SystemMessage(content=[{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}])  # noqa: E501
        return SystemMessage(content=text)
