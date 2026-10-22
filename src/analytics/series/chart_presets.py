from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional

# First Party Imports.
from models.trends.chart_axes import ChartAxes
from models.trends.enums import (
    ChartKind,
    ChartMetric,
    ChartPreset,
    ChartScope,
    MatrixCell,
    PresetFamily,
    SeriesGrouping,
    ValueTransform,
)


class ChartPresets:
    """The ready-made charts: competitive analysis, forecasts and geopolitics, in one click.

    Attributes:
        PRESETS (ClassVar[Dict[ChartPreset, ChartAxes]]): The axes of each ready-made chart.
        FAMILIES (ClassVar[Dict[ChartPreset, PresetFamily]]): The question each ready-made chart answers.
        DEFAULTS (ClassVar[Dict[ChartScope, ChartPreset]]): The ready-made chart shown first in each scope.
        logger (Logger): The presets logger.
    """

    PRESETS: ClassVar[Dict[ChartPreset, ChartAxes]] = {
        ChartPreset.SHARE_RACE: ChartAxes(
            scope=ChartScope.STATISTICS,
            x=ChartMetric.PERIOD,
            y=ChartMetric.SHARE,
            series_by=SeriesGrouping.PLAYER,
        ),
        ChartPreset.REVENUE_OUTLOOK: ChartAxes(
            scope=ChartScope.STATISTICS,
            x=ChartMetric.PERIOD,
            y=ChartMetric.REVENUE,
            series_by=SeriesGrouping.PLAYER,
            forecast=True,
        ),
        ChartPreset.MARKET_SIZE_OUTLOOK: ChartAxes(
            scope=ChartScope.STATISTICS,
            x=ChartMetric.PERIOD,
            y=ChartMetric.MARKET_SIZE,
            series_by=SeriesGrouping.PLAYER,
            forecast=True,
        ),
        ChartPreset.BLOC_MARKET_SHARE: ChartAxes(
            scope=ChartScope.STATISTICS,
            chart=ChartKind.AREA,
            x=ChartMetric.PERIOD,
            y=ChartMetric.SHARE,
            series_by=SeriesGrouping.BLOC,
        ),
        ChartPreset.CATALOGUE_GROWTH: ChartAxes(
            scope=ChartScope.CATALOGUE,
            x=ChartMetric.QUARTER,
            y=ChartMetric.LISTED,
            series_by=SeriesGrouping.PROVIDER,
            forecast=True,
        ),
        ChartPreset.CATALOGUE_BLOCS: ChartAxes(
            scope=ChartScope.CATALOGUE,
            chart=ChartKind.AREA,
            x=ChartMetric.QUARTER,
            y=ChartMetric.LISTED,
            series_by=SeriesGrouping.BLOC,
            transform=ValueTransform.SHARE_OF_TOTAL,
            forecast=True,
        ),
        ChartPreset.CATALOGUE_LAUNCHES: ChartAxes(
            scope=ChartScope.CATALOGUE, x=ChartMetric.YEAR, y=ChartMetric.ADDED, series_by=SeriesGrouping.BLOC
        ),
        ChartPreset.NEW_LISTINGS_BY_BLOC: ChartAxes(
            scope=ChartScope.MARKETPLACE, x=ChartMetric.QUARTER, y=ChartMetric.ADDED, series_by=SeriesGrouping.BLOC
        ),
        ChartPreset.LISTINGS_MOMENTUM: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            x=ChartMetric.QUARTER,
            y=ChartMetric.LISTED,
            series_by=SeriesGrouping.PROVIDER,
            transform=ValueTransform.INDEXED,
        ),
        ChartPreset.DELIVERY_TRENDS: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.AREA,
            x=ChartMetric.QUARTER,
            y=ChartMetric.ADDED,
            series_by=SeriesGrouping.DELIVERY,
        ),
        ChartPreset.PUBLISHER_OVERLAP: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.HEATMAP,
            series_by=SeriesGrouping.PROVIDER,
            columns=SeriesGrouping.PROVIDER,
            cell=MatrixCell.OVERLAP,
        ),
        ChartPreset.DELIVERY_MIX: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.MIX,
            series_by=SeriesGrouping.BLOC,
            columns=SeriesGrouping.DELIVERY,
            cell=MatrixCell.ROW_SHARE,
        ),
        ChartPreset.SHARE_VS_LISTINGS: ChartAxes(
            scope=ChartScope.ANALYSIS,
            chart=ChartKind.BUBBLE,
            x=ChartMetric.SHARE,
            y=ChartMetric.MARKETPLACE_SIZE,
            size=ChartMetric.CATALOGUE_SIZE,
            series_by=SeriesGrouping.PROVIDER,
        ),
        ChartPreset.CATALOGUE_VS_PUBLISHERS: ChartAxes(
            scope=ChartScope.ANALYSIS,
            chart=ChartKind.BUBBLE,
            x=ChartMetric.CATALOGUE_SIZE,
            y=ChartMetric.PUBLISHERS,
            size=ChartMetric.MARKETPLACE_SIZE,
            series_by=SeriesGrouping.PROVIDER,
            log_scale=True,
        ),
        ChartPreset.RANK_RACE: ChartAxes(
            scope=ChartScope.ANALYSIS,
            x=ChartMetric.QUARTER,
            y=ChartMetric.MARKETPLACE_SIZE,
            series_by=SeriesGrouping.PROVIDER,
            transform=ValueTransform.RANK,
        ),
        ChartPreset.BLOC_CATALOGUE: ChartAxes(
            scope=ChartScope.ANALYSIS,
            chart=ChartKind.AREA,
            x=ChartMetric.QUARTER,
            y=ChartMetric.CATALOGUE_SIZE,
            series_by=SeriesGrouping.BLOC,
            transform=ValueTransform.SHARE_OF_TOTAL,
            forecast=True,
        ),
        ChartPreset.DOMAIN_TRENDS_BY_PROVIDER: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.AREA,
            x=ChartMetric.QUARTER,
            y=ChartMetric.LISTED,
            series_by=SeriesGrouping.DOMAIN,
            facet_by=SeriesGrouping.PROVIDER,
            transform=ValueTransform.SHARE_OF_TOTAL,
            top=8,
        ),
        ChartPreset.AUDIENCE_TRENDS: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.AREA,
            x=ChartMetric.QUARTER,
            y=ChartMetric.LISTED,
            series_by=SeriesGrouping.AUDIENCE,
            transform=ValueTransform.SHARE_OF_TOTAL,
        ),
        ChartPreset.AUDIENCE_MIX_BY_PROVIDER: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.MIX,
            series_by=SeriesGrouping.PROVIDER,
            columns=SeriesGrouping.AUDIENCE,
            cell=MatrixCell.ROW_SHARE,
        ),
        ChartPreset.AUDIENCE_BY_PROVIDER: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.AREA,
            x=ChartMetric.QUARTER,
            y=ChartMetric.LISTED,
            series_by=SeriesGrouping.AUDIENCE,
            facet_by=SeriesGrouping.PROVIDER,
            transform=ValueTransform.SHARE_OF_TOTAL,
        ),
        ChartPreset.CATEGORY_MIX_BY_PROVIDER: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.HEATMAP,
            series_by=SeriesGrouping.PROVIDER,
            columns=SeriesGrouping.CATEGORY,
            cell=MatrixCell.ROW_SHARE,
        ),
        ChartPreset.CATALOGUE_DOMAINS_BY_PROVIDER: ChartAxes(
            scope=ChartScope.CATALOGUE,
            chart=ChartKind.MIX,
            series_by=SeriesGrouping.PROVIDER,
            columns=SeriesGrouping.DOMAIN,
            cell=MatrixCell.ROW_SHARE,
        ),
        ChartPreset.DOMAIN_MIX_BY_BLOC: ChartAxes(
            scope=ChartScope.MARKETPLACE,
            chart=ChartKind.MIX,
            series_by=SeriesGrouping.BLOC,
            columns=SeriesGrouping.DOMAIN,
            cell=MatrixCell.ROW_SHARE,
        ),
    }
    FAMILIES: ClassVar[Dict[ChartPreset, PresetFamily]] = {
        ChartPreset.SHARE_RACE: PresetFamily.COMPETITIVE,
        ChartPreset.REVENUE_OUTLOOK: PresetFamily.FORECAST,
        ChartPreset.MARKET_SIZE_OUTLOOK: PresetFamily.FORECAST,
        ChartPreset.BLOC_MARKET_SHARE: PresetFamily.GEOPOLITICS,
        ChartPreset.CATALOGUE_GROWTH: PresetFamily.FORECAST,
        ChartPreset.CATALOGUE_BLOCS: PresetFamily.GEOPOLITICS,
        ChartPreset.CATALOGUE_LAUNCHES: PresetFamily.GEOPOLITICS,
        ChartPreset.NEW_LISTINGS_BY_BLOC: PresetFamily.GEOPOLITICS,
        ChartPreset.LISTINGS_MOMENTUM: PresetFamily.COMPETITIVE,
        ChartPreset.DELIVERY_TRENDS: PresetFamily.FORECAST,
        ChartPreset.PUBLISHER_OVERLAP: PresetFamily.COMPETITIVE,
        ChartPreset.DELIVERY_MIX: PresetFamily.GEOPOLITICS,
        ChartPreset.SHARE_VS_LISTINGS: PresetFamily.COMPETITIVE,
        ChartPreset.CATALOGUE_VS_PUBLISHERS: PresetFamily.COMPETITIVE,
        ChartPreset.RANK_RACE: PresetFamily.COMPETITIVE,
        ChartPreset.BLOC_CATALOGUE: PresetFamily.GEOPOLITICS,
        ChartPreset.DOMAIN_TRENDS_BY_PROVIDER: PresetFamily.COMPETITIVE,
        ChartPreset.AUDIENCE_TRENDS: PresetFamily.COMPETITIVE,
        ChartPreset.AUDIENCE_MIX_BY_PROVIDER: PresetFamily.COMPETITIVE,
        ChartPreset.AUDIENCE_BY_PROVIDER: PresetFamily.COMPETITIVE,
        ChartPreset.CATEGORY_MIX_BY_PROVIDER: PresetFamily.COMPETITIVE,
        ChartPreset.CATALOGUE_DOMAINS_BY_PROVIDER: PresetFamily.COMPETITIVE,
        ChartPreset.DOMAIN_MIX_BY_BLOC: PresetFamily.GEOPOLITICS,
    }
    DEFAULTS: ClassVar[Dict[ChartScope, ChartPreset]] = {
        ChartScope.STATISTICS: ChartPreset.SHARE_RACE,
        ChartScope.CATALOGUE: ChartPreset.CATALOGUE_GROWTH,
        ChartScope.MARKETPLACE: ChartPreset.NEW_LISTINGS_BY_BLOC,
        ChartScope.ANALYSIS: ChartPreset.SHARE_VS_LISTINGS,
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the presets.

        Args:
            logger (Optional[Logger]): The presets logger.
        """
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Publicly Exposed Methods #
    ############################

    def axes(self, preset: ChartPreset) -> ChartAxes:
        """Get the axes of a ready-made chart.

        Args:
            preset (ChartPreset): The ready-made chart.

        Returns:
            ChartAxes: Its axes, naming the preset.
        """
        self.logger.debug("Ready-made chart %s chosen.", preset.value)
        return self.PRESETS[preset].model_copy(update={"preset": preset})

    def family(self, preset: ChartPreset) -> PresetFamily:
        """Get the question a ready-made chart answers.

        Args:
            preset (ChartPreset): The ready-made chart.

        Returns:
            PresetFamily: Its family.
        """
        return self.FAMILIES[preset]

    def for_scope(self, scope: ChartScope) -> List[ChartPreset]:
        """Get the ready-made charts of a scope.

        Args:
            scope (ChartScope): The chart scope.

        Returns:
            List[ChartPreset]: The ready-made charts, grouped by family (competitive, forecast, geopolitics).
        """
        presets = [preset for preset, axes in self.PRESETS.items() if axes.scope is scope]
        families = list(PresetFamily)
        return sorted(presets, key=lambda preset: families.index(self.FAMILIES[preset]))

    def default(self, scope: ChartScope) -> ChartAxes:
        """Get the axes of the chart shown first in a scope.

        Args:
            scope (ChartScope): The chart scope.

        Returns:
            ChartAxes: The axes of its default ready-made chart.
        """
        return self.axes(self.DEFAULTS[scope])
