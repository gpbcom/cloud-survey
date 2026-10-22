from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.configuration.logging.base.base_formatter_config import BaseFormatterConfig
from models.configuration.logging.base.dict_config_model import DictConfigModel


def test_is_a_dict_config_model() -> None:
    assert issubclass(BaseFormatterConfig, DictConfigModel)


def test_defaults() -> None:
    formatter = BaseFormatterConfig()

    assert formatter.datefmt is None
    assert formatter.style == "%"


@pytest.mark.parametrize("style", ["%", "{", "$"])
def test_supported_styles(style: str) -> None:
    assert BaseFormatterConfig.model_validate({"style": style}).style == style


def test_invalid_style_is_rejected() -> None:
    with pytest.raises(ValidationError):
        BaseFormatterConfig.model_validate({"style": "#"})


def test_parses_date_format() -> None:
    assert BaseFormatterConfig.model_validate({"datefmt": "%H:%M"}).datefmt == "%H:%M"


def test_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BaseFormatterConfig.model_validate({"format": "%(message)s"})
