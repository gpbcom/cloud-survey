from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.storage.usage.exception import InvalidLlmCallValueError, LlmCallError
from models.storage.usage.llm_call import LlmCall

VALID: Dict[str, JsonValue] = {"task": "classify-items", "provider": "anthropic", "model": "claude-x"}


class TestLlmCall:
    def test_the_defaults_and_normalized_fields(self) -> None:
        call = LlmCall.model_validate({**VALID, "task": " classify-items ", "currency": "eur", "cost": "0.0125"})

        assert (call.task, call.currency, call.cost) == ("classify-items", "EUR", Decimal("0.0125"))
        assert (call.id, call.called_at, call.input_tokens) == (None, None, 0)

    def test_a_stored_call_reads_its_identifier_and_time(self) -> None:
        call = LlmCall.model_validate({**VALID, "id": 7, "called_at": "2026-10-26T08:00:00+00:00"})

        assert call.id == 7
        assert call.called_at == datetime(2026, 10, 26, 8, 0, tzinfo=UTC)

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("id", "7"),
            ("id", True),
            ("task", ""),
            ("task", "two words"),
            ("provider", 3),
            ("model", None),
            ("input_tokens", 1.5),
            ("output_tokens", "3"),
            ("cache_read_tokens", False),
            ("cost", 0.1),
            ("cost", "a lot"),
            ("cost", None),
            ("currency", "euro"),
            ("currency", 978),
            ("called_at", "yesterday"),
            ("called_at", "2026-10-26T08:00:00"),
            ("called_at", 1761465600),
        ],
    )
    def test_an_invalid_field_is_refused_with_its_error(self, field: str, value: JsonValue) -> None:
        with pytest.raises(ValidationError) as caught:
            LlmCall.model_validate({**VALID, field: value})

        error = caught.value.errors()[0].get("ctx", {}).get("error")
        assert isinstance(error, InvalidLlmCallValueError)
        assert isinstance(error, LlmCallError)

    def test_a_negative_count_or_cost_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            LlmCall.model_validate({**VALID, "output_tokens": -1})
        with pytest.raises(ValidationError):
            LlmCall.model_validate({**VALID, "cost": "-0.5"})

    def test_the_error_names_the_field_and_what_it_expects(self) -> None:
        error = InvalidLlmCallValueError("currency", "euro", "three letters (ISO 4217)")

        assert (error.field, error.value, error.expected) == ("currency", "euro", "three letters (ISO 4217)")
        assert str(error) == "The currency of a language model call is 'euro': expected three letters (ISO 4217)."
