from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple

# Third Party Imports.
from PyQt6.QtGui import QColor

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import CloudProvider, DeliveryMethod, GeoBloc, MarketPlayer, SoftwareAudience
from models.taxonomy.nodes.taxonomy import Taxonomy
from models.trends.enums import (
    ChartKind,
    ChartMetric,
    ChartNote,
    ChartPreset,
    ChartScope,
    MatrixCell,
    MetricUnit,
    OptionBlock,
    PresetFamily,
    SeriesGrouping,
    ValueTransform,
)
from taxonomy.seed_loader import TaxonomySeedLoader


class ChartLabels:
    """Name the chart options, axes and series for people, and colour the series consistently across charts.

    Attributes:
        METRIC_LABELS (ClassVar[Dict[ChartMetric, str]]): The display name of each metric.
        ITEM_METRICS (ClassVar[Dict[ChartMetric, str]]): The metrics counting the items of the chart, by verb.
        ITEM_NOUNS (ClassVar[Dict[ChartScope, str]]): What the items of each scope are.
        GROUPING_LABELS (ClassVar[Dict[SeriesGrouping, str]]): The display name of each grouping.
        GROUPING_PLURALS (ClassVar[Dict[SeriesGrouping, str]]): The plural of each grouping, in the titles.
        TRANSFORM_LABELS (ClassVar[Dict[ValueTransform, str]]): The display name of each value transform.
        KIND_LABELS (ClassVar[Dict[ChartKind, str]]): The display name of each chart kind.
        KIND_TIPS (ClassVar[Dict[ChartKind, str]]): What each chart kind shows, as a tooltip.
        CELL_LABELS (ClassVar[Dict[MatrixCell, str]]): The display name of each matrix cell metric.
        PRESET_LABELS (ClassVar[Dict[ChartPreset, str]]): The display name of each ready-made chart.
        FAMILY_LABELS (ClassVar[Dict[PresetFamily, str]]): The display name of each ready-made chart family.
        BLOCK_LABELS (ClassVar[Dict[OptionBlock, str]]): Why an option cannot be chosen, for people.
        NOTE_LABELS (ClassVar[Dict[ChartNote, str]]): The footnote of each caveat.
        UNIT_SUFFIXES (ClassVar[Dict[MetricUnit, str]]): The unit shown after an axis title.
        SERIES_PALETTE (ClassVar[Tuple[str, ...]]): The colours of the delivery methods (Okabe-Ito, colour-blind
            safe, then lighter tones).
        OTHERS_COLOR (ClassVar[str]): The colour of the series merging the smallest ones.
        SHADE_STEP (ClassVar[int]): How much lighter each category of a domain is than the previous one, in percent.
        theme (Theme): The application theme.
        taxonomy (Optional[Taxonomy]): The unified taxonomy naming the category and domain series, read from the seed
            of the project when first needed (unless given).
        logger (Logger): The labels logger.
    """

    METRIC_LABELS: ClassVar[Dict[ChartMetric, str]] = {
        ChartMetric.PERIOD: "Period",
        ChartMetric.PUBLISHED: "Publication date",
        ChartMetric.YEAR: "Year",
        ChartMetric.QUARTER: "Quarter",
        ChartMetric.MONTH: "Month",
        ChartMetric.CRAWL_DATE: "Crawl date",
        ChartMetric.SHARE: "Market share",
        ChartMetric.REVENUE: "Revenue",
        ChartMetric.MARKET_SIZE: "Market size",
        ChartMetric.TWELVE_MONTH: "12-month market size",
        ChartMetric.GROWTH: "Market growth",
        ChartMetric.ADDED: "Added",
        ChartMetric.DELETED: "Deleted",
        ChartMetric.UPDATED: "Updated",
        ChartMetric.LISTED: "Listed",
        ChartMetric.CATALOGUE_SIZE: "Catalogue size",
        ChartMetric.MARKETPLACE_SIZE: "Marketplace size",
        ChartMetric.PUBLISHERS: "Publishers",
    }
    ITEM_METRICS: ClassVar[Dict[ChartMetric, str]] = {
        ChartMetric.ADDED: "added",
        ChartMetric.DELETED: "deleted",
        ChartMetric.UPDATED: "updated",
        ChartMetric.LISTED: "listed",
    }
    ITEM_NOUNS: ClassVar[Dict[ChartScope, str]] = {
        ChartScope.CATALOGUE: "products",
        ChartScope.MARKETPLACE: "software",
    }
    GROUPING_LABELS: ClassVar[Dict[SeriesGrouping, str]] = {
        SeriesGrouping.PLAYER: "Player",
        SeriesGrouping.PROVIDER: "Provider",
        SeriesGrouping.BLOC: "Bloc",
        SeriesGrouping.DELIVERY: "Delivery",
        SeriesGrouping.AUDIENCE: "Audience",
        SeriesGrouping.CATEGORY: "Category",
        SeriesGrouping.DOMAIN: "Domain",
    }
    GROUPING_PLURALS: ClassVar[Dict[SeriesGrouping, str]] = {
        SeriesGrouping.PLAYER: "player",
        SeriesGrouping.PROVIDER: "provider",
        SeriesGrouping.BLOC: "bloc",
        SeriesGrouping.DELIVERY: "delivery method",
        SeriesGrouping.AUDIENCE: "audience",
        SeriesGrouping.CATEGORY: "category",
        SeriesGrouping.DOMAIN: "domain",
    }
    TRANSFORM_LABELS: ClassVar[Dict[ValueTransform, str]] = {
        ValueTransform.RAW: "Values",
        ValueTransform.SHARE_OF_TOTAL: "Share of total",
        ValueTransform.INDEXED: "Indexed (first = 100)",
        ValueTransform.YOY: "Year-on-year change",
        ValueTransform.RANK: "Rank",
    }
    KIND_LABELS: ClassVar[Dict[ChartKind, str]] = {
        ChartKind.LINE: "Line",
        ChartKind.AREA: "Area",
        ChartKind.BUBBLE: "Bubble",
        ChartKind.HEATMAP: "Heatmap",
        ChartKind.MIX: "Mix",
    }
    KIND_TIPS: ClassVar[Dict[ChartKind, str]] = {
        ChartKind.LINE: "Lines over time or over another metric",
        ChartKind.AREA: "Stacked areas over time: totals and shares",
        ChartKind.BUBBLE: "Competitive positioning: one bubble per provider",
        ChartKind.HEATMAP: "A matrix of coloured cells, rows by columns",
        ChartKind.MIX: "One 100% bar per row: the mix of its columns",
    }
    CELL_LABELS: ClassVar[Dict[MatrixCell, str]] = {
        MatrixCell.LISTED: "Listed software",
        MatrixCell.ROW_SHARE: "Share of the row",
        MatrixCell.PUBLISHERS: "Publishers",
        MatrixCell.SHARED_PUBLISHERS: "Shared publishers",
        MatrixCell.OVERLAP: "Publisher overlap",
    }
    PRESET_LABELS: ClassVar[Dict[ChartPreset, str]] = {
        ChartPreset.SHARE_RACE: "Market share race",
        ChartPreset.MARKET_SIZE_OUTLOOK: "Market size outlook",
        ChartPreset.REVENUE_OUTLOOK: "Revenue outlook per player",
        ChartPreset.BLOC_MARKET_SHARE: "Market share by bloc",
        ChartPreset.CATALOGUE_GROWTH: "Catalogue growth outlook",
        ChartPreset.CATALOGUE_BLOCS: "United States vs European Union vs China vs Russia",
        ChartPreset.CATALOGUE_LAUNCHES: "Product launches per year, by bloc",
        ChartPreset.NEW_LISTINGS_BY_BLOC: "New listings by bloc",
        ChartPreset.LISTINGS_MOMENTUM: "Listings momentum (indexed)",
        ChartPreset.DELIVERY_TRENDS: "New listings by delivery method",
        ChartPreset.PUBLISHER_OVERLAP: "Publisher overlap between marketplaces",
        ChartPreset.DELIVERY_MIX: "Delivery mix by bloc",
        ChartPreset.SHARE_VS_LISTINGS: "Market share vs marketplace size",
        ChartPreset.CATALOGUE_VS_PUBLISHERS: "Catalogue vs publishers",
        ChartPreset.RANK_RACE: "Marketplace size rank race",
        ChartPreset.BLOC_CATALOGUE: "Catalogue share by bloc, with forecast",
        ChartPreset.DOMAIN_TRENDS_BY_PROVIDER: "Domain mix over time, by provider",
        ChartPreset.AUDIENCE_TRENDS: "Developer tools vs end-user software (and both) over time",
        ChartPreset.AUDIENCE_MIX_BY_PROVIDER: "Audience mix by provider: developers, business users or both",
        ChartPreset.AUDIENCE_BY_PROVIDER: "Audience mix over time, by provider",
        ChartPreset.CATEGORY_MIX_BY_PROVIDER: "Category mix by provider",
        ChartPreset.CATALOGUE_DOMAINS_BY_PROVIDER: "Catalogue domains by provider",
        ChartPreset.DOMAIN_MIX_BY_BLOC: "Domain mix by bloc",
    }
    FAMILY_LABELS: ClassVar[Dict[PresetFamily, str]] = {
        PresetFamily.COMPETITIVE: "Competitive analysis",
        PresetFamily.FORECAST: "Forecast",
        PresetFamily.GEOPOLITICS: "Geopolitics",
    }
    BLOCK_LABELS: ClassVar[Dict[OptionBlock, str]] = {
        OptionBlock.SAME_AS_X: "Already shown on another axis",
        OptionBlock.NEEDS_TIME_AXIS: "Needs a time x axis",
        OptionBlock.NEEDS_NUMERIC_AXIS: "Needs a measured x axis, not a time axis",
        OptionBlock.NEEDS_CALENDAR_AXIS: "Needs years, quarters, months or periods on the x axis",
        OptionBlock.NOT_ADDITIVE: "These values cannot be added up",
        OptionBlock.NOT_PER_GROUPING: "Not known per value of this grouping",
        OptionBlock.NOT_FROM_CRAWLS: "Not recorded by the crawls",
        OptionBlock.SAME_AS_ROWS: "Already the rows",
        OptionBlock.NEEDS_PROVIDERS: "Compares marketplaces: the rows and columns must be providers",
        OptionBlock.NO_CATALOGUES: "No catalogue stored yet: crawl the catalogues first",
        OptionBlock.NO_MARKETPLACES: "No marketplace stored yet: crawl the marketplaces first",
        OptionBlock.NO_STATISTICS: "No market statistics yet: refresh them from Synergy first",
        OptionBlock.SAME_AS_SERIES: "Already the grouping of the series",
    }
    NOTE_LABELS: ClassVar[Dict[ChartNote, str]] = {
        ChartNote.FIRST_CRAWL_DATES: "Items without a published date are dated by the crawl which first found them",
        ChartNote.PLAYER_PROVIDERS: "Synergy publishes the shares of AWS, Azure, Google Cloud and T Cloud only",
        ChartNote.MIXED_CURRENCIES: "Amounts in several currencies (USD and EUR)",
        ChartNote.METHODOLOGY_BREAK: "Dashed amber lines: methodology change, not comparable with earlier periods",
        ChartNote.PUBLISHERS_FIRST_SEEN: "Publishers count from their first listing and are never removed",
        ChartNote.FORECAST_METHOD: "Forecast: least-squares trend of the last 8 points, not a prediction",
        ChartNote.CRAWL_HISTORY: "Crawl records start with the first crawl stored in the database",
    }
    UNIT_SUFFIXES: ClassVar[Dict[MetricUnit, str]] = {
        MetricUnit.PERCENT: "%",
        MetricUnit.BILLIONS: "bn",
        MetricUnit.INDEX: "first = 100",
    }
    SERIES_PALETTE: ClassVar[Tuple[str, ...]] = (
        "#56B4E9",
        "#E69F00",
        "#009E73",
        "#F0E442",
        "#0072B2",
        "#D55E00",
        "#CC79A7",
        "#8DD3C7",
        "#BEBADA",
        "#FB8072",
        "#80B1D3",
        "#FDB462",
    )
    OTHERS_COLOR: ClassVar[str] = "#6b7486"
    SHADE_STEP: ClassVar[int] = 22

    def __init__(self, theme: Theme, logger: Optional[Logger] = None, taxonomy: Optional[Taxonomy] = None) -> None:
        """Initialize the labels.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The labels logger.
            taxonomy (Optional[Taxonomy]): The unified taxonomy, the seed of the project (read when first needed) by
                default.
        """
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.taxonomy = taxonomy

    ############################
    # Internal Helpers Methods #
    ############################

    def _palette(self, index: int) -> QColor:
        """Get a colour of the series palette.

        Args:
            index (int): The position of the value in its enum.

        Returns:
            QColor: The colour, the palette repeating itself.
        """
        return QColor(self.SERIES_PALETTE[index % len(self.SERIES_PALETTE)])

    def _taxonomy(self) -> Taxonomy:
        """Get the taxonomy naming the category and domain series, reading the seed the first time.

        Returns:
            Taxonomy: The unified taxonomy.
        """
        if self.taxonomy is None:
            self.logger.debug("Reading the taxonomy seed for the chart labels.")
            self.taxonomy = TaxonomySeedLoader(self.logger).load_taxonomy()
        return self.taxonomy

    def _node_color(self, slug: str) -> QColor:
        """Colour a taxonomy node: one hue per domain, its categories in lighter shades of it.

        Args:
            slug (str): The node slug.

        Returns:
            QColor: The colour, that of the merged series for an unknown node.
        """
        taxonomy = self._taxonomy()
        domain = taxonomy.domain_of(slug)
        if domain is None:
            return QColor(self.OTHERS_COLOR)
        domains = [node.slug for node in taxonomy.domains()]
        base = self._palette(domains.index(domain))
        if domain == slug:
            return base
        siblings = [node.slug for node in taxonomy.children(domain)]
        return base.lighter(100 + self.SHADE_STEP * (siblings.index(slug) % 6))

    ############################
    # Publicly Exposed Methods #
    ############################

    def metric_label(self, metric: ChartMetric, scope: ChartScope) -> str:
        """Name a metric, the counted items named after the scope.

        Args:
            metric (ChartMetric): The metric.
            scope (ChartScope): The chart scope.

        Returns:
            str: e.g. `Listed products`, `Added software` or `Market share`.
        """
        noun = self.ITEM_NOUNS.get(scope)
        if metric in self.ITEM_METRICS and noun:
            return f"{self.METRIC_LABELS[metric]} {noun}"
        return self.METRIC_LABELS[metric]

    def axis_title(self, metric: ChartMetric, scope: ChartScope, transform: ValueTransform = ValueTransform.RAW) -> str:
        """Title an axis: its metric, transform and unit.

        Args:
            metric (ChartMetric): The metric of the axis.
            scope (ChartScope): The chart scope.
            transform (ValueTransform): How its values are transformed.

        Returns:
            str: e.g. `Market share (%)`, `Listed products, share of total (%)` or `Rank by marketplace size`.
        """
        label = self.metric_label(metric, scope)
        match transform:
            case ValueTransform.SHARE_OF_TOTAL:
                return f"{label}, share of total (%)"
            case ValueTransform.INDEXED:
                return f"{label} (first = 100)"
            case ValueTransform.YOY:
                return f"{label}, year on year (%)"
            case ValueTransform.RANK:
                return f"Rank by {label.lower()}"
            case _:
                suffix = self.UNIT_SUFFIXES.get(metric.unit)
                return f"{label} ({suffix})" if suffix else label

    def series_label(self, grouping: SeriesGrouping, key: str) -> str:
        """Name a series.

        Args:
            grouping (SeriesGrouping): What the series stand for.
            key (str): The value of the grouping enum, `*` for the merged series, empty for the whole market.

        Returns:
            str: e.g. `AWS`, `European Union`, `SaaS`, `Others` or `Market`, the key itself when unknown.
        """
        if key == "*":
            return "Others"
        if not key:
            return "Market"
        try:
            match grouping:
                case SeriesGrouping.PLAYER:
                    return self.theme.player_label(MarketPlayer(key))
                case SeriesGrouping.PROVIDER:
                    return self.theme.PROVIDER_SHORT_LABELS[CloudProvider(key)]
                case SeriesGrouping.BLOC:
                    return self.theme.bloc_label(GeoBloc(key))
                case SeriesGrouping.DELIVERY:
                    return self.theme.delivery_label(DeliveryMethod(key))
                case SeriesGrouping.AUDIENCE:
                    return self.theme.audience_label(SoftwareAudience(key))
                case _:
                    node = self._taxonomy().node(key)
                    return node.name_en if node is not None else key
        except ValueError:
            self.logger.debug("Unknown %s series key %r.", grouping.value, key)
            return key

    def series_color(self, grouping: SeriesGrouping, key: str) -> QColor:
        """Colour a series the same way in every chart.

        Args:
            grouping (SeriesGrouping): What the series stand for.
            key (str): The value of the grouping enum, `*` for the merged series, empty for the whole market.

        Returns:
            QColor: The provider, player or bloc colour, a palette colour for the deliveries, a domain shade for the
                taxonomy nodes.
        """
        if key == "*":
            return QColor(self.OTHERS_COLOR)
        if not key:
            return QColor(self.theme.ACCENT)
        try:
            match grouping:
                case SeriesGrouping.PLAYER:
                    return self.theme.player_color(MarketPlayer(key))
                case SeriesGrouping.PROVIDER:
                    return self.theme.provider_color(CloudProvider(key))
                case SeriesGrouping.BLOC:
                    return self.theme.bloc_color(GeoBloc(key))
                case SeriesGrouping.DELIVERY:
                    return self._palette(list(DeliveryMethod).index(DeliveryMethod(key)))
                case SeriesGrouping.AUDIENCE:
                    return self.theme.audience_color(SoftwareAudience(key))
                case _:
                    return self._node_color(key)
        except ValueError:
            self.logger.debug("Unknown %s series key %r.", grouping.value, key)
            return QColor(self.OTHERS_COLOR)

    def bloc_of(self, grouping: SeriesGrouping, key: str) -> Optional[GeoBloc]:
        """Get the bloc a series belongs to.

        Args:
            grouping (SeriesGrouping): What the series stand for.
            key (str): The value of the grouping enum.

        Returns:
            Optional[GeoBloc]: The bloc of the provider, player or bloc, `None` for the other groupings.
        """
        try:
            match grouping:
                case SeriesGrouping.PROVIDER:
                    return CloudProvider(key).bloc
                case SeriesGrouping.PLAYER:
                    return MarketPlayer(key).bloc
                case SeriesGrouping.BLOC:
                    return GeoBloc(key)
                case _:
                    return None
        except ValueError:
            return None
