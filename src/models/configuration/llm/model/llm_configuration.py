from __future__ import annotations

# Standard Library Imports.
import os
from decimal import Decimal
from typing import Optional

# Third Party Imports.
from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, field_validator

# First Party Imports.
from models.configuration.llm.enums import LLMEffort, LLMProvider


class LLMConfiguration(BaseModel):
    """A language model: its provider, name, key, limits and prices.

    Attributes:
        provider (LLMProvider): The provider.
        model_name (str): The model (e.g. `claude-haiku-5-5`).
        api_key (Optional[SecretStr]): The API key, read from the environment variable named in the file, `None` when
            that variable is not set (the model is then not configured).
        temperature (Optional[float]): The sampling temperature, `None` for the models which take none (the current
            Claude models reject it).
        max_tokens (int): The largest number of output tokens of a call.
        effort (Optional[LLMEffort]): How much the model thinks, `None` for its default.
        input_rate_per_million (Decimal): The price of a million input tokens.
        output_rate_per_million (Decimal): The price of a million output tokens.
        cache_read_rate_per_million (Optional[Decimal]): The price of a million input tokens read from the prompt
            cache, the tenth of the input rate when not given.

    Notes:
        The file names the environment variable holding the key (e.g. `ANTHROPIC_API_KEY`), never the key itself.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: LLMProvider = Field(default=LLMProvider.ANTHROPIC, description="The provider.")
    model_name: str = Field(min_length=1, description="The model.")
    api_key: Optional[SecretStr] = Field(default=None, description="The API key, from the named variable.")
    temperature: Optional[float] = Field(default=None, le=2.0, description="The sampling temperature.")
    max_tokens: int = Field(default=4096, gt=0, le=128_000, description="The largest number of output tokens.")
    effort: Optional[LLMEffort] = Field(default=None, description="How much the model thinks.")
    input_rate_per_million: Decimal = Field(default=Decimal(0), ge=0, description="The input price per million.")
    output_rate_per_million: Decimal = Field(default=Decimal(0), ge=0, description="The output price per million.")
    cache_read_rate_per_million: Optional[Decimal] = Field(
        default=None, ge=0, description="The cached input price per million."
    )

    @field_validator("api_key", mode="before")
    def validate_api_key(cls, value: JsonValue) -> JsonValue:
        """Read the API key from the environment variable named in the file.

        Args:
            value (JsonValue): The name of the environment variable (e.g. `ANTHROPIC_API_KEY`).

        Returns:
            JsonValue: The key, `None` when the variable is unset or blank.
        """
        if isinstance(value, str):
            key = os.getenv(value.strip(), "").strip()
            return key or None
        return value

    @field_validator("temperature", mode="before")
    def validate_temperature(cls, value: JsonValue) -> JsonValue:
        """Clamp a negative temperature to 0.

        Args:
            value (JsonValue): The raw temperature.

        Returns:
            JsonValue: The temperature, 0 when negative.
        """
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
            return 0.0
        return value

    @field_validator("model_name", mode="before")
    def validate_model_name(cls, value: JsonValue) -> JsonValue:
        """Trim the model name.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The trimmed name.
        """
        return value.strip() if isinstance(value, str) else value

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_configured(self) -> bool:
        """Tell whether the model can be called.

        Returns:
            bool: Whether its API key is set.
        """
        return self.api_key is not None

    def cache_read_rate(self) -> Decimal:
        """Get the price of a million input tokens read from the prompt cache.

        Returns:
            Decimal: The configured rate, else the tenth of the input rate.
        """
        if self.cache_read_rate_per_million is not None:
            return self.cache_read_rate_per_million
        return self.input_rate_per_million / 10
