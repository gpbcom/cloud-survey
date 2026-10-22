from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication

from analytics.series.axis_rules import AxisRules
from analytics.series.chart_presets import ChartPresets
from gui.charts.common.chart_labels import ChartLabels
from gui.theme import Theme
from models.trends.chart_axes import ChartAxes
from models.trends.enums import ChartKind, ChartPreset, ChartScope, MatrixCell, SeriesGrouping


@pytest.mark.parametrize("scope", [ChartScope.CATALOGUE, ChartScope.MARKETPLACE])
def test_both_kinds_of_items_are_grouped_by_category_and_domain(scope: ChartScope) -> None:
    rules = AxisRules()
    options = dict(rules.groupings(ChartAxes(scope=scope)))

    assert options[SeriesGrouping.CATEGORY] is None
    assert options[SeriesGrouping.DOMAIN] is None
    assert SeriesGrouping.DOMAIN in dict(rules.facet_options(ChartAxes(scope=scope)))


def test_the_catalogue_has_matrices_without_software_fields() -> None:
    rules = AxisRules()
    axes = ChartAxes(scope=ChartScope.CATALOGUE, chart=ChartKind.HEATMAP, series_by=SeriesGrouping.PROVIDER)

    assert ChartKind.HEATMAP in rules.kinds(ChartScope.CATALOGUE)
    assert [grouping for grouping, _ in rules.groupings(axes)] == [
        SeriesGrouping.PROVIDER,
        SeriesGrouping.BLOC,
        SeriesGrouping.AUDIENCE,
        SeriesGrouping.DOMAIN,
        SeriesGrouping.CATEGORY,
    ]
    assert rules.cell_options(axes) == [MatrixCell.LISTED, MatrixCell.ROW_SHARE]
    repaired = rules.repair(axes.model_copy(update={"columns": SeriesGrouping.DELIVERY, "cell": MatrixCell.OVERLAP}))
    assert (repaired.columns, repaired.cell) == (SeriesGrouping.BLOC, MatrixCell.LISTED)


@pytest.mark.parametrize(
    "preset",
    [ChartPreset.CATEGORY_MIX_BY_PROVIDER, ChartPreset.CATALOGUE_DOMAINS_BY_PROVIDER, ChartPreset.DOMAIN_MIX_BY_BLOC],
)
def test_the_taxonomy_presets_are_valid(preset: ChartPreset) -> None:
    axes = ChartPresets.PRESETS[preset]

    assert AxisRules().is_valid(axes)
    assert preset in ChartPresets.FAMILIES
    assert ChartLabels.PRESET_LABELS[preset]


def test_category_series_are_named_and_shaded_by_domain(qapp: QApplication) -> None:
    labels = ChartLabels(Theme())

    assert labels.series_label(SeriesGrouping.CATEGORY, "relational-database") == "Relational databases"
    assert labels.series_label(SeriesGrouping.DOMAIN, "databases") == "Databases"
    assert labels.series_label(SeriesGrouping.CATEGORY, "nowhere") == "nowhere"
    domain = labels.series_color(SeriesGrouping.DOMAIN, "databases")
    first = labels.series_color(SeriesGrouping.CATEGORY, "database")
    second = labels.series_color(SeriesGrouping.CATEGORY, "relational-database")
    assert first == domain, "the first category of a domain has the domain colour"
    assert second.hue() == domain.hue()
    assert second.lightness() > domain.lightness()
    assert labels.series_color(SeriesGrouping.DOMAIN, "databases") != labels.series_color(
        SeriesGrouping.DOMAIN, "compute"
    )
    assert labels.GROUPING_LABELS[SeriesGrouping.CATEGORY] == "Category"
