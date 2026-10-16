from __future__ import annotations

import pytest
from pydantic import Field, ValidationError

from models.configuration.logging.base.dict_config_model import DictConfigModel


class SampleModel(DictConfigModel):
    """Model with an aliased field, mimicking a `dictConfig` camelCase key."""

    max_bytes: int = Field(default=0, alias="maxBytes")


def test_validates_by_alias() -> None:
    assert SampleModel.model_validate({"maxBytes": 5}).max_bytes == 5


def test_validates_by_field_name() -> None:
    assert SampleModel.model_validate({"max_bytes": 5}).max_bytes == 5
    assert SampleModel(max_bytes=5).max_bytes == 5


def test_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SampleModel.model_validate({"maxbytes": 5})


def test_dumps_by_alias_on_demand() -> None:
    model = SampleModel(max_bytes=5)

    assert model.model_dump() == {"max_bytes": 5}
    assert model.model_dump(by_alias=True) == {"maxBytes": 5}
