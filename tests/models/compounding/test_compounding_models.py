from __future__ import annotations

from typing import Dict

import pytest
from pydantic import JsonValue, ValidationError

from models.cloud.enums import CloudProvider, DateCaveat
from models.compounding.compounding_query import CompoundingQuery
from models.compounding.config.compounding_config import CompoundingConfig
from models.compounding.config.compounding_settings import CompoundingSettings
from models.compounding.config.foundations.category_foundations import CategoryFoundations
from models.compounding.config.market_size_point import MarketSizePoint
from models.compounding.config.scope.excluded_provider import ExcludedProvider
from models.compounding.config.scope.provider_scope import ProviderScope
from models.compounding.help.compounding_help import CompoundingHelp
from models.compounding.help.help_entry import HelpEntry
from models.compounding.results.fits.estimate import Estimate
from models.compounding.results.scores.transfer_score import TransferScore

LINK: Dict[str, JsonValue] = {"foundation": "virtual-machines", "source": "https://example.com"}


def config(**changes: JsonValue) -> Dict[str, JsonValue]:
    raw: Dict[str, JsonValue] = {
        "providers": [{"provider": "amazon-web-services", "start": "2006", "source": "https://example.com"}],
        "domains": ["compute"],
        "foundations": [{"category": "kubernetes", "links": [LINK]}],
    }
    raw.update(changes)
    return raw


def test_a_valid_configuration_reads_its_parts() -> None:
    parsed = CompoundingConfig.model_validate(
        config(market=[{"year": "2014", "size_bn": "15.5", "source": "https://x.y"}])
    )

    assert parsed.kept() == [CloudProvider.AWS]
    assert parsed.start(CloudProvider.AWS) == 2006
    assert parsed.start(CloudProvider.GCP) is None
    assert parsed.foundation_sets() == {"kubernetes": ["virtual-machines"]}
    assert parsed.market_sizes() == {2014: 15.5}
    assert parsed.settings == CompoundingSettings()


@pytest.mark.parametrize(
    "changes",
    [
        {"providers": []},
        {"providers": [{"provider": "amazon-web-services"}, {"provider": "amazon-web-services"}]},
        {"providers": [{"provider": "not-a-provider"}]},
        {"domains": ["Compute"]},
        {"domains": ["compute", "compute"]},
        {"foundations": [{"category": "kubernetes", "links": [{"foundation": "kubernetes", "source": "https://x.y"}]}]},
        {"foundations": [{"category": "kubernetes", "links": [LINK]}, {"category": "kubernetes", "links": [LINK]}]},
        {
            "market": [
                {"year": 2014, "size_bn": 1, "source": "https://x.y"},
                {"year": 2014, "size_bn": 2, "source": "https://x.y"},
            ]
        },
        {"settings": "fast"},
    ],
)
def test_an_invalid_configuration_is_refused(changes: Dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        CompoundingConfig.model_validate(config(**changes))


@pytest.mark.parametrize(
    "raw",
    [
        {"provider": "amazon-web-services", "start": "1980"},
        {"provider": "amazon-web-services", "start": "20x6"},
        {"provider": "amazon-web-services", "source": "not a link"},
    ],
)
def test_an_invalid_provider_scope_is_refused(raw: Dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        ProviderScope.model_validate(raw)


def test_an_exclusion_needs_a_reason() -> None:
    with pytest.raises(ValidationError):
        ExcludedProvider.model_validate({"provider": "china-telecom-cloud", "reason": "no"})


@pytest.mark.parametrize(
    "raw",
    [
        {"category": "Kubernetes", "links": [LINK]},
        {"category": "kubernetes", "links": []},
        {"category": "kubernetes", "links": [LINK, LINK]},
        {"category": "kubernetes", "links": [{"foundation": "virtual machines", "source": "https://x.y"}]},
        {"category": "kubernetes", "links": [{"foundation": "virtual-machines", "source": "ftp://x"}]},
    ],
)
def test_an_invalid_foundation_set_is_refused(raw: Dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        CategoryFoundations.model_validate(raw)


@pytest.mark.parametrize(
    "raw",
    [
        {"year": 1999, "size_bn": 1, "source": "https://x.y"},
        {"year": 2014, "size_bn": 0, "source": "https://x.y"},
        {"year": 2014, "size_bn": 1, "source": "x"},
    ],
)
def test_an_invalid_market_size_is_refused(raw: Dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        MarketSizePoint.model_validate(raw)


@pytest.mark.parametrize(
    "raw",
    [
        {"lags": [0]},
        {"lags": [1, 1]},
        {"bootstrap": -1},
        {"min_events": 0},
        {"precedence_share": 0.5},
        {"held_caveats": ["feed-start", "feed-start"]},
        {"held_caveats": ["not-a-caveat"]},
        {"last_year": 2001},
    ],
)
def test_invalid_settings_are_refused(raw: Dict[str, JsonValue]) -> None:
    with pytest.raises(ValidationError):
        CompoundingSettings.model_validate(raw)


def test_the_settings_sort_the_lags_and_read_the_caveats() -> None:
    settings = CompoundingSettings.model_validate({"lags": [3, 1], "held_caveats": ["feed-start"]})

    assert settings.lags == [1, 3]
    assert settings.held_caveats == [DateCaveat.FEED_START]


def test_the_help_refuses_a_key_explained_twice() -> None:
    entry = {"key": "run", "title": "Run", "text": "Run the analysis."}

    with pytest.raises(ValidationError):
        CompoundingHelp.model_validate({"controls": [entry, entry]})
    with pytest.raises(ValidationError):
        HelpEntry.model_validate({"key": "Run", "title": "Run", "text": "Run the analysis."})


def test_the_help_gives_titles_and_texts() -> None:
    help_texts = CompoundingHelp.model_validate(
        {"controls": [{"key": "run", "title": "Run", "text": "Run the analysis."}]}
    )

    assert help_texts.title("controls", "run") == "Run"
    assert help_texts.text("controls", "run") == "Run the analysis."
    assert help_texts.title("controls", "lag") == "lag"
    assert help_texts.text("cards", "lag") == ""


def test_the_query_keeps_each_provider_once() -> None:
    query = CompoundingQuery.model_validate({"providers": ["amazon-web-services", "amazon-web-services", "scaleway"]})

    assert query.providers == [CloudProvider.AWS, CloudProvider.SCALEWAY]
    with pytest.raises(ValidationError):
        CompoundingQuery(lag=0)


def test_an_estimate_is_significant_when_its_interval_excludes_zero() -> None:
    assert Estimate(name="x", value=1.0, low=0.2, high=2.0).significant()
    assert not Estimate(name="x", value=1.0, low=-0.2, high=2.0).significant()
    assert not Estimate(name="x", value=1.0).significant()


def test_the_transfer_gain_needs_both_areas() -> None:
    assert TransferScore(
        provider=CloudProvider.GCP, rows=10, events=2, auc=0.7, baseline_auc=0.6
    ).gain() == pytest.approx(0.1)
    assert TransferScore(provider=CloudProvider.GCP, rows=10, events=0).gain() is None
