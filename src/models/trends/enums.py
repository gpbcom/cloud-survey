from __future__ import annotations

# Standard Library Imports.
from enum import StrEnum, unique
from typing import Dict, Final, FrozenSet, Optional, Tuple

# First Party Imports.
from models.storage.enums import DatasetKind


@unique
class MetricKind(StrEnum):
    """Enums representing what the values of a chart metric are.

    Attributes:
        TIME (str): Moments in time: periods, buckets or dates, as month ordinals.
        NUMERIC (str): Measured quantities.
    """

    TIME = "time"
    NUMERIC = "numeric"


@unique
class MetricUnit(StrEnum):
    """Enums representing the unit of the values of a chart axis.

    Attributes:
        DATE (str): Moments in time.
        COUNT (str): Numbers of products, software or publishers.
        PERCENT (str): Percentages.
        BILLIONS (str): Amounts, in billions of the report currency.
        INDEX (str): Values indexed to 100 at the first point.
        RANK (str): Ranks, 1 being the highest value.
    """

    DATE = "date"
    COUNT = "count"
    PERCENT = "percent"
    BILLIONS = "billions"
    INDEX = "index"
    RANK = "rank"


@unique
class ForecastMethod(StrEnum):
    """Enums representing how the trend of a series is extrapolated.

    Attributes:
        LINEAR (str): Least-squares straight line.
        LOG_LINEAR (str): Least-squares straight line on the logarithm of the values: a constant growth rate.
    """

    LINEAR = "linear"
    LOG_LINEAR = "log-linear"


@unique
class ChartMetric(StrEnum):
    """Enums representing the metrics a chart axis can show.

    Attributes:
        PERIOD (str): The period of a market report (quarter, half-year or year).
        PUBLISHED (str): When a market report was published.
        YEAR (str): The year bucket of the history dates.
        QUARTER (str): The quarter bucket of the history dates.
        MONTH (str): The month bucket of the history dates.
        CRAWL_DATE (str): When a crawl started.
        SHARE (str): The market share of a player, in percent.
        REVENUE (str): The revenue of a player: its share of the market size, in billions.
        MARKET_SIZE (str): The market size over a period, in billions.
        TWELVE_MONTH (str): The market size over the twelve months ending with a period, in billions.
        GROWTH (str): The year-on-year growth of the market, in percent.
        ADDED (str): The number of items added in a bucket (or by a crawl).
        DELETED (str): The number of items deleted in a bucket (or by a crawl).
        UPDATED (str): The number of items updated by the crawls of a bucket (or by a crawl).
        LISTED (str): The number of items listed at the end of a bucket (or after a crawl).
        CATALOGUE_SIZE (str): The number of catalogue products listed at the end of a bucket.
        MARKETPLACE_SIZE (str): The number of marketplace software listed at the end of a bucket.
        PUBLISHERS (str): The number of distinct marketplace publishers ever listed at the end of a bucket.
    """

    PERIOD = "period"
    PUBLISHED = "published"
    YEAR = "year"
    QUARTER = "quarter"
    MONTH = "month"
    CRAWL_DATE = "crawl-date"
    SHARE = "share"
    REVENUE = "revenue"
    MARKET_SIZE = "market-size"
    TWELVE_MONTH = "twelve-month"
    GROWTH = "growth"
    ADDED = "added"
    DELETED = "deleted"
    UPDATED = "updated"
    LISTED = "listed"
    CATALOGUE_SIZE = "catalogue-size"
    MARKETPLACE_SIZE = "marketplace-size"
    PUBLISHERS = "publishers"

    @property
    def kind(self) -> MetricKind:
        """Get what the values of the metric are.

        Returns:
            MetricKind: `TIME` for the periods, buckets and dates, `NUMERIC` otherwise.
        """
        return MetricKind.TIME if self in TIME_METRICS else MetricKind.NUMERIC

    @property
    def unit(self) -> MetricUnit:
        """Get the unit of the metric values.

        Returns:
            MetricUnit: The unit.
        """
        return METRIC_UNITS.get(self, MetricUnit.COUNT)

    @property
    def bounds(self) -> Tuple[Optional[float], Optional[float]]:
        """Get the range the values of the metric (and their forecast) stay in.

        Returns:
            Tuple[Optional[float], Optional[float]]: The lowest and highest values, `None` when unbounded.
        """
        return METRIC_BOUNDS.get(self, (0.0, None))

    @property
    def forecast_method(self) -> ForecastMethod:
        """Get how the trend of the metric is extrapolated: growth rates compound for the sizes.

        Returns:
            ForecastMethod: The forecast method.
        """
        return ForecastMethod.LOG_LINEAR if self in COMPOUNDING_METRICS else ForecastMethod.LINEAR

    @property
    def stock(self) -> bool:
        """Tell whether the metric is a level (carried forward when a point is missing) rather than a flow.

        Returns:
            bool: `False` for the additions, deletions and updates (a missing point is none of them).
        """
        return self not in FLOW_METRICS

    @property
    def additive(self) -> bool:
        """Tell whether the values of several series can be summed (stacked, or as shares of their total).

        Returns:
            bool: Whether the metric is additive.
        """
        return self in ADDITIVE_METRICS

    @property
    def from_crawls(self) -> bool:
        """Tell whether the metric is recorded by each crawl, so that it can be shown per crawl date.

        Returns:
            bool: Whether the metric is recorded by the crawls.
        """
        return self in CRAWL_METRICS

    @property
    def player_scoped(self) -> bool:
        """Tell whether the metric is given per market player (rather than per market report).

        Returns:
            bool: Whether the metric is given per player.
        """
        return self in PLAYER_METRICS

    @property
    def source(self) -> Optional[DatasetKind]:
        """Get the dataset the metric is always read from.

        Returns:
            Optional[DatasetKind]: The dataset, `None` when the metric is read from the dataset of the chart.
        """
        return METRIC_SOURCES.get(self)


@unique
class SeriesGrouping(StrEnum):
    """Enums representing what each series (or each matrix row or column) of a chart stands for.

    Attributes:
        PLAYER (str): A market player.
        PROVIDER (str): A cloud provider.
        BLOC (str): A geopolitical bloc.
        DELIVERY (str): A software delivery method.
        AUDIENCE (str): Who the software is meant for: developers only, business users only, or both.
        CATEGORY (str): A category of the unified taxonomy (an item in several categories counts in each).
        DOMAIN (str): A domain of the unified taxonomy (an item in several domains counts in each).
    """

    PLAYER = "player"
    PROVIDER = "provider"
    BLOC = "bloc"
    DELIVERY = "delivery"
    AUDIENCE = "audience"
    CATEGORY = "category"
    DOMAIN = "domain"


@unique
class ValueTransform(StrEnum):
    """Enums representing how the values of the series are transformed before they are shown.

    Attributes:
        RAW (str): The values as they are.
        SHARE_OF_TOTAL (str): The share of each series in the total of every series at the same point, in percent.
        INDEXED (str): The values indexed to 100 at the first point of each series.
        YOY (str): The change from the value twelve months before, in percent.
        RANK (str): The rank of each series among every series at the same point, 1 being the highest.
    """

    RAW = "raw"
    SHARE_OF_TOTAL = "share-of-total"
    INDEXED = "indexed"
    YOY = "yoy"
    RANK = "rank"

    @property
    def unit(self) -> Optional[MetricUnit]:
        """Get the unit of the transformed values.

        Returns:
            Optional[MetricUnit]: The unit, `None` when the values keep the unit of their metric.
        """
        return TRANSFORM_UNITS.get(self)


@unique
class ChartKind(StrEnum):
    """Enums representing the kinds of charts.

    Attributes:
        LINE (str): Lines over a time or numeric x axis.
        AREA (str): Stacked areas over time.
        BUBBLE (str): One bubble per series, positioned by two metrics and sized by a third.
        HEATMAP (str): A matrix of coloured cells, rows by columns.
        MIX (str): One 100% stacked bar per row, a segment per column.
    """

    LINE = "line"
    AREA = "area"
    BUBBLE = "bubble"
    HEATMAP = "heatmap"
    MIX = "mix"

    @property
    def is_matrix(self) -> bool:
        """Tell whether the chart shows a matrix (rows by columns) rather than series.

        Returns:
            bool: Whether the chart is a heatmap or a mix of bars.
        """
        return self in MATRIX_KINDS


@unique
class MatrixCell(StrEnum):
    """Enums representing what the cells of a matrix chart count.

    Attributes:
        LISTED (str): The number of listed items of the row and the column.
        ROW_SHARE (str): The share of the row items in the column, in percent.
        PUBLISHERS (str): The number of distinct publishers of the row and the column.
        SHARED_PUBLISHERS (str): The number of publishers listed by both marketplaces.
        OVERLAP (str): The Jaccard overlap of the publishers of both marketplaces, in percent.
    """

    LISTED = "listed"
    ROW_SHARE = "row-share"
    PUBLISHERS = "publishers"
    SHARED_PUBLISHERS = "shared-publishers"
    OVERLAP = "overlap"

    @property
    def unit(self) -> MetricUnit:
        """Get the unit of the cell values.

        Returns:
            MetricUnit: `PERCENT` for the shares and the overlap, `COUNT` otherwise.
        """
        return MetricUnit.PERCENT if self in (MatrixCell.ROW_SHARE, MatrixCell.OVERLAP) else MetricUnit.COUNT

    @property
    def publisher_pairs(self) -> bool:
        """Tell whether the cell compares the publishers of two marketplaces (provider rows and columns).

        Returns:
            bool: Whether the cell compares two marketplaces.
        """
        return self in (MatrixCell.SHARED_PUBLISHERS, MatrixCell.OVERLAP)


@unique
class ChartScope(StrEnum):
    """Enums representing where a chart is shown, which sets the data it reads.

    Attributes:
        STATISTICS (str): The market statistics tab.
        CATALOGUE (str): The product catalogues tab.
        MARKETPLACE (str): The marketplaces tab.
        ANALYSIS (str): The cross-dataset analysis tab.
    """

    STATISTICS = "statistics"
    CATALOGUE = "catalogue"
    MARKETPLACE = "marketplace"
    ANALYSIS = "analysis"

    @property
    def dataset(self) -> Optional[DatasetKind]:
        """Get the dataset the metrics of the scope are read from, unless they name their own.

        Returns:
            Optional[DatasetKind]: The dataset, `None` for the analysis (every metric names its dataset).
        """
        return SCOPE_DATASETS.get(self)


@unique
class PresetFamily(StrEnum):
    """Enums representing the questions the ready-made charts answer.

    Attributes:
        COMPETITIVE (str): How the providers compare.
        FORECAST (str): Where the trends lead.
        GEOPOLITICS (str): How the United States, the European Union and China compare.
    """

    COMPETITIVE = "competitive"
    FORECAST = "forecast"
    GEOPOLITICS = "geopolitics"


@unique
class ChartPreset(StrEnum):
    """Enums representing the ready-made charts.

    Attributes:
        SHARE_RACE (str): The market shares of the players over the periods.
        MARKET_SIZE_OUTLOOK (str): The market size over the periods, with its forecast.
        REVENUE_OUTLOOK (str): The revenue of the players over the periods, with its forecast.
        BLOC_MARKET_SHARE (str): The market share of each bloc over the periods.
        CATALOGUE_GROWTH (str): The listed products per provider over time, with their forecast.
        CATALOGUE_BLOCS (str): The share of each bloc in the listed products over time, with its forecast.
        CATALOGUE_LAUNCHES (str): The products added each year, per bloc.
        NEW_LISTINGS_BY_BLOC (str): The software added each quarter, per bloc.
        LISTINGS_MOMENTUM (str): The listed software per provider over time, indexed to 100.
        DELIVERY_TRENDS (str): The software added each quarter, per delivery method.
        PUBLISHER_OVERLAP (str): The publishers shared by each pair of marketplaces.
        DELIVERY_MIX (str): The delivery methods of the listed software of each bloc.
        SHARE_VS_LISTINGS (str): The market share against the marketplace size, sized by the catalogue.
        CATALOGUE_VS_PUBLISHERS (str): The catalogue size against the publishers, sized by the marketplace.
        RANK_RACE (str): The rank of the providers by marketplace size over time.
        BLOC_CATALOGUE (str): The share of each bloc in the listed products over time, with its forecast.
        DOMAIN_TRENDS_BY_PROVIDER (str): The share of each taxonomy domain in the listed software over time, one chart
            per provider.
        AUDIENCE_TRENDS (str): The share of the developer tools, the end-user software and the software meant for both
            in the listed software over time.
        AUDIENCE_MIX_BY_PROVIDER (str): The developer tools, end-user software and software for both of each provider.
        AUDIENCE_BY_PROVIDER (str): The audience shares of the listed software over time, one chart per provider.
        CATEGORY_MIX_BY_PROVIDER (str): The share of each category in the listed software of each provider.
        CATALOGUE_DOMAINS_BY_PROVIDER (str): The share of each domain in the listed products of each provider.
        DOMAIN_MIX_BY_BLOC (str): The share of each domain in the listed software of each bloc.
    """

    SHARE_RACE = "share-race"
    MARKET_SIZE_OUTLOOK = "market-size-outlook"
    REVENUE_OUTLOOK = "revenue-outlook"
    BLOC_MARKET_SHARE = "bloc-market-share"
    CATALOGUE_GROWTH = "catalogue-growth"
    CATALOGUE_BLOCS = "catalogue-blocs"
    CATALOGUE_LAUNCHES = "catalogue-launches"
    NEW_LISTINGS_BY_BLOC = "new-listings-by-bloc"
    LISTINGS_MOMENTUM = "listings-momentum"
    DELIVERY_TRENDS = "delivery-trends"
    PUBLISHER_OVERLAP = "publisher-overlap"
    DELIVERY_MIX = "delivery-mix"
    SHARE_VS_LISTINGS = "share-vs-listings"
    CATALOGUE_VS_PUBLISHERS = "catalogue-vs-publishers"
    RANK_RACE = "rank-race"
    BLOC_CATALOGUE = "bloc-catalogue"
    DOMAIN_TRENDS_BY_PROVIDER = "domain-trends-by-provider"
    AUDIENCE_TRENDS = "audience-trends"
    AUDIENCE_MIX_BY_PROVIDER = "audience-mix-by-provider"
    AUDIENCE_BY_PROVIDER = "audience-by-provider"
    CATEGORY_MIX_BY_PROVIDER = "category-mix-by-provider"
    CATALOGUE_DOMAINS_BY_PROVIDER = "catalogue-domains-by-provider"
    DOMAIN_MIX_BY_BLOC = "domain-mix-by-bloc"


@unique
class OptionBlock(StrEnum):
    """Enums representing why a chart option cannot be chosen with the other options.

    Attributes:
        SAME_AS_X (str): The metric is already on another axis.
        NEEDS_TIME_AXIS (str): The option needs a time x axis.
        NEEDS_NUMERIC_AXIS (str): The option needs a numeric x axis.
        NEEDS_CALENDAR_AXIS (str): The option needs an x axis of calendar buckets or periods.
        NOT_ADDITIVE (str): The values of several series cannot be summed.
        NOT_PER_GROUPING (str): The metric is not known per value of the chosen grouping.
        NOT_FROM_CRAWLS (str): The metric is not recorded by the crawls.
        SAME_AS_ROWS (str): The grouping is already the grouping of the rows.
        NEEDS_PROVIDERS (str): The cell compares marketplaces: the rows and columns must be providers.
        NO_CATALOGUES (str): No catalogue is stored yet.
        NO_MARKETPLACES (str): No marketplace is stored yet.
        NO_STATISTICS (str): No market statistics are stored yet.
        SAME_AS_SERIES (str): The grouping is already the grouping of the series.
    """

    SAME_AS_X = "same-as-x"
    NEEDS_TIME_AXIS = "needs-time-axis"
    NEEDS_NUMERIC_AXIS = "needs-numeric-axis"
    NEEDS_CALENDAR_AXIS = "needs-calendar-axis"
    NOT_ADDITIVE = "not-additive"
    NOT_PER_GROUPING = "not-per-grouping"
    NOT_FROM_CRAWLS = "not-from-crawls"
    SAME_AS_ROWS = "same-as-rows"
    NEEDS_PROVIDERS = "needs-providers"
    NO_CATALOGUES = "no-catalogues"
    NO_MARKETPLACES = "no-marketplaces"
    NO_STATISTICS = "no-statistics"
    SAME_AS_SERIES = "same-as-series"


@unique
class ChartNote(StrEnum):
    """Enums representing the caveats a chart footnote warns about.

    Attributes:
        FIRST_CRAWL_DATES (str): Items without a published date are dated by the crawl which first found them.
        PLAYER_PROVIDERS (str): The market statistics quantify a few crawled providers only.
        MIXED_CURRENCIES (str): The amounts are in several currencies.
        METHODOLOGY_BREAK (str): Some periods are not comparable with the previous ones.
        PUBLISHERS_FIRST_SEEN (str): The publishers are counted from their first listing, never removed.
        FORECAST_METHOD (str): How the forecast is computed.
        CRAWL_HISTORY (str): The updates are only known since the first crawl stored in the database.
    """

    FIRST_CRAWL_DATES = "first-crawl-dates"
    PLAYER_PROVIDERS = "player-providers"
    MIXED_CURRENCIES = "mixed-currencies"
    METHODOLOGY_BREAK = "methodology-break"
    PUBLISHERS_FIRST_SEEN = "publishers-first-seen"
    FORECAST_METHOD = "forecast-method"
    CRAWL_HISTORY = "crawl-history"


TIME_METRICS: Final[FrozenSet[ChartMetric]] = frozenset(
    {
        ChartMetric.PERIOD,
        ChartMetric.PUBLISHED,
        ChartMetric.YEAR,
        ChartMetric.QUARTER,
        ChartMetric.MONTH,
        ChartMetric.CRAWL_DATE,
    }
)

METRIC_UNITS: Final[Dict[ChartMetric, MetricUnit]] = {
    **{metric: MetricUnit.DATE for metric in TIME_METRICS},
    ChartMetric.SHARE: MetricUnit.PERCENT,
    ChartMetric.GROWTH: MetricUnit.PERCENT,
    ChartMetric.REVENUE: MetricUnit.BILLIONS,
    ChartMetric.MARKET_SIZE: MetricUnit.BILLIONS,
    ChartMetric.TWELVE_MONTH: MetricUnit.BILLIONS,
}

METRIC_BOUNDS: Final[Dict[ChartMetric, Tuple[Optional[float], Optional[float]]]] = {
    ChartMetric.SHARE: (0.0, 100.0),
    ChartMetric.GROWTH: (None, None),
}

COMPOUNDING_METRICS: Final[FrozenSet[ChartMetric]] = frozenset(
    {
        ChartMetric.REVENUE,
        ChartMetric.MARKET_SIZE,
        ChartMetric.TWELVE_MONTH,
        ChartMetric.LISTED,
        ChartMetric.CATALOGUE_SIZE,
        ChartMetric.MARKETPLACE_SIZE,
        ChartMetric.PUBLISHERS,
    }
)

FLOW_METRICS: Final[FrozenSet[ChartMetric]] = frozenset({ChartMetric.ADDED, ChartMetric.DELETED, ChartMetric.UPDATED})

ADDITIVE_METRICS: Final[FrozenSet[ChartMetric]] = frozenset(
    {
        ChartMetric.SHARE,
        ChartMetric.REVENUE,
        ChartMetric.ADDED,
        ChartMetric.DELETED,
        ChartMetric.UPDATED,
        ChartMetric.LISTED,
        ChartMetric.CATALOGUE_SIZE,
        ChartMetric.MARKETPLACE_SIZE,
    }
)

CRAWL_METRICS: Final[FrozenSet[ChartMetric]] = frozenset(
    {ChartMetric.ADDED, ChartMetric.DELETED, ChartMetric.UPDATED, ChartMetric.LISTED}
)

PLAYER_METRICS: Final[FrozenSet[ChartMetric]] = frozenset({ChartMetric.SHARE, ChartMetric.REVENUE})

METRIC_SOURCES: Final[Dict[ChartMetric, DatasetKind]] = {
    ChartMetric.PERIOD: DatasetKind.STATISTICS,
    ChartMetric.PUBLISHED: DatasetKind.STATISTICS,
    ChartMetric.SHARE: DatasetKind.STATISTICS,
    ChartMetric.REVENUE: DatasetKind.STATISTICS,
    ChartMetric.MARKET_SIZE: DatasetKind.STATISTICS,
    ChartMetric.TWELVE_MONTH: DatasetKind.STATISTICS,
    ChartMetric.GROWTH: DatasetKind.STATISTICS,
    ChartMetric.CATALOGUE_SIZE: DatasetKind.CATALOGUE,
    ChartMetric.MARKETPLACE_SIZE: DatasetKind.MARKETPLACE,
    ChartMetric.PUBLISHERS: DatasetKind.MARKETPLACE,
}

TRANSFORM_UNITS: Final[Dict[ValueTransform, MetricUnit]] = {
    ValueTransform.SHARE_OF_TOTAL: MetricUnit.PERCENT,
    ValueTransform.INDEXED: MetricUnit.INDEX,
    ValueTransform.YOY: MetricUnit.PERCENT,
    ValueTransform.RANK: MetricUnit.RANK,
}

MATRIX_KINDS: Final[FrozenSet[ChartKind]] = frozenset({ChartKind.HEATMAP, ChartKind.MIX})

SCOPE_DATASETS: Final[Dict[ChartScope, DatasetKind]] = {
    ChartScope.STATISTICS: DatasetKind.STATISTICS,
    ChartScope.CATALOGUE: DatasetKind.CATALOGUE,
    ChartScope.MARKETPLACE: DatasetKind.MARKETPLACE,
}
