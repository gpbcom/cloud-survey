from __future__ import annotations

from typing import Dict

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

from models.cloud.enums import CloudProvider, PriceModel
from models.cloud.prices import exception as errors
from models.cloud.prices.coverage.coverage_catalog import CoverageCatalog
from models.cloud.prices.coverage.coverage_statement import CoverageStatement

STATEMENT: Dict[str, JsonValue] = {
    "product": "Azure Advisor",
    "model": "free",
    "reason": "Azure Advisor is free of charge.",
    "source": "https://azure.microsoft.com/en-us/products/advisor",
}


def error_of(model: type[BaseModel], data: Dict[str, JsonValue]) -> type[Exception]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(data)
    error = caught.value.errors()[0].get("ctx", {}).get("error")
    assert isinstance(error, errors.PriceModelError), caught.value
    return type(error)


class TestCoverageStatement:
    def test_a_statement_is_read(self) -> None:
        statement = CoverageStatement.model_validate(STATEMENT)

        assert (statement.product, statement.model) == ("Azure Advisor", PriceModel.FREE)

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("product", "", errors.InvalidCoverageProductError),
            ("model", "on-demand", errors.InvalidCoverageModelError),
            ("reason", 5, errors.InvalidCoverageReasonError),
            ("source", "azure.microsoft.com", errors.InvalidCoverageSourceError),
        ],
    )
    def test_each_field_raises_its_own_error(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        assert error_of(CoverageStatement, {**STATEMENT, field: value}) is error


class TestCoverageCatalog:
    def test_a_catalogue_is_read(self) -> None:
        catalog = CoverageCatalog.model_validate(
            {
                "provider": "microsoft-azure",
                "currency": "eur",
                "links": {"Azure Cache for Redis": ["^Redis Cache$"]},
                "statements": [STATEMENT],
                "pages": {"Azure Advisor": ["https://example.com/advisor/pricing"]},
            }
        )

        assert (catalog.provider, catalog.currency, catalog.statements[0].product) == (
            CloudProvider.AZURE,
            "EUR",
            "Azure Advisor",
        )
        assert catalog.pages == {"Azure Advisor": ["https://example.com/advisor/pricing"]}
        assert CoverageCatalog.model_validate({"provider": "civo", "links": None, "statements": None}).links == {}
        assert CoverageCatalog.model_validate({"provider": "civo", "pages": None}).pages == {}

    @pytest.mark.parametrize(
        ("field", "value", "error"),
        [
            ("provider", "azure", errors.InvalidProviderError),
            ("links", {"Redis": "^Redis"}, errors.InvalidCoverageLinksError),
            ("links", {"Redis": ["(unclosed"]}, errors.InvalidCoverageLinksError),
            ("statements", "none", errors.InvalidCoverageStatementsError),
            ("row_links", {"Archive": ["[bad"]}, errors.InvalidCoverageRowLinksError),
            ("currency", "euro", errors.InvalidCurrencyError),
            ("pages", {"Advisor": "https://example.com"}, errors.InvalidCoveragePagesError),
            ("pages", {"Advisor": ["ftp://example.com/p"]}, errors.InvalidCoveragePagesError),
        ],
    )
    def test_each_field_raises_its_own_error(self, field: str, value: JsonValue, error: type[Exception]) -> None:
        assert error_of(CoverageCatalog, {"provider": "civo", field: value}) is error
