from __future__ import annotations

# Standard Library Imports.
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import ClassVar, Optional, Pattern

# Third Party Imports.
from pydantic import AwareDatetime, BaseModel, Field, JsonValue, field_validator

# First Party Imports.
from models.storage.usage.exception import InvalidLlmCallValueError


class LlmCall(BaseModel):
    """A recorded language model call: its task, model, tokens and cost.

    Attributes:
        CURRENCY (ClassVar[Pattern[str]]): The format of a currency: three upper-case letters.
        IDENTIFIER (ClassVar[Pattern[str]]): The format of a task, provider or model name.
        id (Optional[int]): The identifier of the stored call, `None` before it is stored.
        task (str): The task of the call, e.g. `classify-items`.
        provider (str): The provider of the model.
        model (str): The model.
        input_tokens (int): The uncached input tokens.
        output_tokens (int): The output tokens.
        cache_read_tokens (int): The input tokens read from the cache.
        cache_write_tokens (int): The input tokens written to the cache.
        cost (Decimal): What the call cost.
        currency (str): The currency of the cost.
        called_at (Optional[AwareDatetime]): When the call was recorded, `None` before it is stored.
    """

    CURRENCY: ClassVar[Pattern[str]] = re.compile(r"^[A-Z]{3}$")
    IDENTIFIER: ClassVar[Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$")

    id: Optional[int] = Field(default=None, ge=1, description="The identifier of the stored call.")
    task: str = Field(min_length=1, max_length=40, description="The task of the call.")
    provider: str = Field(min_length=1, max_length=20, description="The provider of the model.")
    model: str = Field(min_length=1, max_length=100, description="The model.")
    input_tokens: int = Field(default=0, ge=0, description="The uncached input tokens.")
    output_tokens: int = Field(default=0, ge=0, description="The output tokens.")
    cache_read_tokens: int = Field(default=0, ge=0, description="The input tokens read from the cache.")
    cache_write_tokens: int = Field(default=0, ge=0, description="The input tokens written to the cache.")
    cost: Decimal = Field(default=Decimal(0), ge=0, description="What the call cost.")
    currency: str = Field(default="USD", description="The currency of the cost.")
    called_at: Optional[AwareDatetime] = Field(default=None, description="When the call was recorded.")

    @field_validator("id", mode="before")
    def validate_id(cls, value: JsonValue) -> JsonValue:
        """Validate the raw identifier: empty or a whole number.

        Args:
            value (JsonValue): The raw identifier.

        Returns:
            JsonValue: The identifier.

        Raises:
            InvalidLlmCallValueError: If it is not a whole number.
        """
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise InvalidLlmCallValueError("id", str(value), "a whole number")
        return value

    @field_validator("task", "provider", "model", mode="before")
    def validate_name(cls, value: JsonValue) -> JsonValue:
        """Validate a raw task, provider or model name: a text without spaces.

        Args:
            value (JsonValue): The raw name.

        Returns:
            JsonValue: The name, trimmed.

        Raises:
            InvalidLlmCallValueError: If it is not a text without spaces.
        """
        if not isinstance(value, str) or not cls.IDENTIFIER.match(value.strip()):
            raise InvalidLlmCallValueError("name", str(value), "a name of letters, digits and ._:/@-")
        return value.strip()

    @field_validator("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", mode="before")
    def validate_tokens(cls, value: JsonValue) -> JsonValue:
        """Validate a raw token count: a whole number.

        Args:
            value (JsonValue): The raw count.

        Returns:
            JsonValue: The count.

        Raises:
            InvalidLlmCallValueError: If it is not a whole number.
        """
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidLlmCallValueError("token count", str(value), "a whole number")
        return value

    @field_validator("cost", mode="before")
    def validate_cost(cls, value: JsonValue) -> JsonValue:
        """Validate the raw cost: an exact decimal number (a float is refused, money is never binary).

        Args:
            value (JsonValue): The raw cost.

        Returns:
            JsonValue: The cost.

        Raises:
            InvalidLlmCallValueError: If it is a float, or not a number.
        """
        if isinstance(value, Decimal):
            return value
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise InvalidLlmCallValueError("cost", str(value), "a decimal number (never a float)")
        try:
            Decimal(value)
        except InvalidOperation as e:
            raise InvalidLlmCallValueError("cost", str(value), "a decimal number") from e
        return value

    @field_validator("currency", mode="before")
    def validate_currency(cls, value: JsonValue) -> JsonValue:
        """Validate the raw currency: three letters, upper-cased.

        Args:
            value (JsonValue): The raw currency.

        Returns:
            JsonValue: The currency.

        Raises:
            InvalidLlmCallValueError: If it is not three letters.
        """
        currency = value.strip().upper() if isinstance(value, str) else ""
        if not cls.CURRENCY.match(currency):
            raise InvalidLlmCallValueError("currency", str(value), "three letters (ISO 4217)")
        return currency

    @field_validator("called_at", mode="before")
    def validate_called_at(cls, value: JsonValue) -> JsonValue:
        """Validate the raw call time: empty, a date-time or its ISO text, with a time zone.

        Args:
            value (JsonValue): The raw time.

        Returns:
            JsonValue: The time.

        Raises:
            InvalidLlmCallValueError: If it is not a date-time with a time zone.
        """
        if value is None:
            return value
        if isinstance(value, str):
            try:
                moment = datetime.fromisoformat(value)
            except ValueError as e:
                raise InvalidLlmCallValueError("call time", value, "an ISO date-time") from e
            if moment.tzinfo is None:
                raise InvalidLlmCallValueError("call time", value, "a date-time with a time zone")
            return value
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise InvalidLlmCallValueError("call time", str(value), "a date-time with a time zone")
        return value
