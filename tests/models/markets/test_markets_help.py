from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import pytest

from crawler.exception import MarketsCatalogError
from crawler.markets.catalog_loader import MarketsCatalogLoader
from models.markets.enums import (
    AreaKind,
    CorrelationCounterpart,
    Device,
    MarketControl,
    PriceScale,
    ShareMetric,
    ShareSource,
    StockView,
)
from models.markets.help.markets_help import MarketsHelp


@pytest.fixture(scope="module")
def shipped() -> MarketsHelp:
    return MarketsCatalogLoader().help()


def test_every_control_is_explained(shipped: MarketsHelp) -> None:
    assert [control for control in MarketControl if shipped.control(control) is None] == []


@pytest.mark.parametrize(
    ("control", "options"),
    [
        (MarketControl.AGAINST, [kind.value for kind in CorrelationCounterpart]),
        (MarketControl.DEVICE, [device.value for device in Device]),
        (MarketControl.AREA, [kind.value for kind in AreaKind]),
        (MarketControl.VIEW, [view.value for view in StockView]),
        (MarketControl.SCALE, [scale.value for scale in PriceScale]),
        (MarketControl.CURRENCY, ["listing", "USD", "EUR", "GBP"]),
        (MarketControl.SEGMENT, [source.value for source in ShareSource] + [metric.value for metric in ShareMetric]),
    ],
    ids=lambda value: value.value if isinstance(value, MarketControl) else "",
)
def test_every_choice_of_a_list_is_explained(shipped: MarketsHelp, control: MarketControl, options: List[str]) -> None:
    assert [option for option in options if shipped.option(control, option) is None] == []


def test_the_method_names_every_figure_it_is_filled_with(shipped: MarketsHelp) -> None:
    filled = shipped.method.format(lags=12, block=6, resamples=400, granger=3, points=36, gap=3, unit="months")

    assert "-12 to +12 months" in filled
    assert "400 resamples" in filled


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("markets:\n  controls: [{control: zoom, title: Zoom, summary: x}]\n", "content is invalid"),
        ("markets:\n  controls: [\n", "not valid YAML"),
        ("drivers: {}\n", "no `markets` block"),
    ],
)
def test_a_bad_explanations_file_is_reported(tmp_path: Path, content: str, reason: str) -> None:
    path = tmp_path / "help.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(MarketsCatalogError, match=reason):
        MarketsCatalogLoader().help(path)


def test_a_missing_explanations_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(MarketsCatalogError, match="cannot be read"):
        MarketsCatalogLoader().help(tmp_path / "missing.yaml")


def test_the_control_help_lookups_return_none_when_unexplained() -> None:
    explanations = MarketsHelp()
    pairs: List[Tuple[MarketControl, str]] = [(MarketControl.TOP, "x")]

    assert explanations.control(MarketControl.TOP) is None
    assert all(explanations.option(control, option) is None for control, option in pairs)
