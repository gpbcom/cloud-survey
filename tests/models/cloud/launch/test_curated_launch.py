from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import LaunchPrecision
from models.cloud.exception import InvalidLaunchFieldError, MissingLaunchReasonError, MissingLaunchSourceError
from models.cloud.launch.curated_launch import CuratedLaunch

SOURCE = "https://azure.microsoft.com/en-us/blog/announcing-cosmos-db/"


def launch(**fields: JsonValue) -> CuratedLaunch:
    raw: Dict[str, JsonValue] = {"crawler": "azure", "name": "Azure Cosmos DB", "launched": "2014-08", "source": SOURCE}
    return CuratedLaunch.model_validate({**raw, **fields})


@pytest.mark.parametrize(
    ("launched", "precision", "day"),
    [
        ("2014", LaunchPrecision.YEAR, datetime(2014, 1, 1, tzinfo=UTC)),
        ("2014-08", LaunchPrecision.MONTH, datetime(2014, 8, 1, tzinfo=UTC)),
        ("2014-08-21", LaunchPrecision.DAY, datetime(2014, 8, 21, tzinfo=UTC)),
    ],
)
def test_launch_precision_follows_its_format(launched: str, precision: LaunchPrecision, day: datetime) -> None:
    entry = launch(launched=launched)

    assert entry.launched == launched
    assert entry.precision() is precision
    assert entry.launch_date() == day


def test_yaml_values_are_accepted_as_years_and_days() -> None:
    assert launch(launched=2014).launched == "2014"
    assert launch(launched=date(2014, 8, 21)).launched == "2014-08-21"  # type: ignore[arg-type]


@pytest.mark.parametrize("launched", ["14-08", "2014/08", "2014-13", "2014-02-30", "1989", "2999", "August 2014"])
def test_rejects_an_invalid_launch(launched: str) -> None:
    with pytest.raises(ValidationError) as error:
        launch(launched=launched)

    assert isinstance(error.value.errors()[0]["ctx"]["error"], InvalidLaunchFieldError)


def test_names_are_trimmed_and_crawlers_checked() -> None:
    assert launch(name="  Azure   Cosmos DB ").name == "Azure Cosmos DB"
    for crawler in ("Azure", "az ure", "", 3):
        with pytest.raises(ValidationError):
            launch(crawler=crawler)
    with pytest.raises(ValidationError):
        launch(name="x" * 121)


def test_source_must_be_an_absolute_link() -> None:
    assert launch(source=f"  {SOURCE} ").source == SOURCE
    for source in ("azure.microsoft.com/blog", "ftp://example.com/launch", 42):
        with pytest.raises(ValidationError):
            launch(source=source)


def test_a_launch_must_cite_its_source() -> None:
    with pytest.raises(ValidationError) as error:
        launch(source=None)

    assert isinstance(error.value.errors()[0]["ctx"]["error"], MissingLaunchSourceError)


def test_a_known_gap_has_a_reason_and_no_date() -> None:
    gap = launch(launched=None, source=None, reason="  No announcement found,  the product was renamed. ")

    assert gap.reason == "No announcement found, the product was renamed."
    assert gap.precision() is None
    assert gap.launch_date() is None


def test_a_product_without_launch_must_say_why() -> None:
    with pytest.raises(ValidationError) as error:
        launch(launched=None, source=None, reason="  ")

    assert isinstance(error.value.errors()[0]["ctx"]["error"], MissingLaunchReasonError)
    with pytest.raises(ValidationError):
        launch(launched=None, reason="x" * 301)


def test_is_frozen_and_strict() -> None:
    with pytest.raises(ValidationError):
        launch(extra="field")
    with pytest.raises(ValidationError):
        launch().name = "Other"  # type: ignore[misc]
