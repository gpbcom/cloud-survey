from __future__ import annotations

# Standard Library Imports.
import html
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

# First Party Imports.
from gui.statistics.market_size_chart import MarketSizeChart, SizeBar
from gui.statistics.perimeter_panel import PerimeterPanel
from gui.statistics.share_bar import ShareBar
from gui.statistics.share_bar_chart import ShareBarChart, ShareGroup
from gui.statistics.share_trend_chart import ShareTrendChart, TrendSeries
from gui.theme import Theme
from models.cloud.enums import MarketPlayer, MarketRegion, MarketSegment
from models.stats.market_report import MarketReport
from models.stats.market_statistics import MarketStatistics

GroupKey = Tuple[MarketRegion, MarketSegment]


class StatisticsView(QWidget):
    """Cloud market statistics: market shares of the latest selected period, their trend and the market size.

    The perimeter (regions, segments, providers and periods) is chosen with checkboxes. The share of the others is
    computed as 100% minus the published shares, and the providers named without a share are listed.

    Attributes:
        REGION_TAGS (ClassVar[Dict[MarketRegion, str]]): The short tag of each region, in the trend and size charts.
        LINE_STYLES (ClassVar[Tuple[Qt.PenStyle, ...]]): The trend line style of each region and segment, in order.
        SEGMENT_TAGS (ClassVar[Dict[MarketSegment, str]]): The short tag of each segment, in the trend chart.
        refresh_requested (pyqtSignal): Emitted when the statistics should be crawled again.
        theme (Theme): The application theme.
        statistics (Optional[MarketStatistics]): The shown statistics, `None` before the first crawl.
        panel (PerimeterPanel): The perimeter checkboxes.
        source_label (QLabel): The source of the figures, linking to the article.
        share_chart (ShareBarChart): The market shares of the latest selected period.
        trend_chart (ShareTrendChart): The market shares over the selected periods.
        size_chart (MarketSizeChart): The market size of the selected periods.
        mentions_label (QLabel): The providers named without a market share.
        empty_label (QLabel): Shown when there are no statistics.
        refresh_button (QPushButton): Requests a new crawl of the statistics.
    """

    REGION_TAGS: ClassVar[Dict[MarketRegion, str]] = {MarketRegion.WORLDWIDE: "WW", MarketRegion.EUROPE: "EU"}
    LINE_STYLES: ClassVar[Tuple[Qt.PenStyle, ...]] = (
        Qt.PenStyle.SolidLine,
        Qt.PenStyle.DashLine,
        Qt.PenStyle.DotLine,
        Qt.PenStyle.DashDotLine,
    )
    SEGMENT_TAGS: ClassVar[Dict[MarketSegment, str]] = {
        MarketSegment.CLOUD_INFRASTRUCTURE: "CIS",
        MarketSegment.PUBLIC_IAAS_PAAS: "public",
    }

    refresh_requested = pyqtSignal()

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build the view, without statistics.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The view logger.
        """
        super().__init__()
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.statistics: Optional[MarketStatistics] = None
        self.panel = PerimeterPanel(theme)
        self.source_label = QLabel()
        self.source_label.setObjectName("muted")
        self.source_label.setTextFormat(Qt.TextFormat.RichText)
        self.source_label.setOpenExternalLinks(True)
        self.source_label.setWordWrap(True)
        self.share_chart = ShareBarChart(theme)
        self.trend_chart = ShareTrendChart(theme)
        self.size_chart = MarketSizeChart(theme)
        self.mentions_label = QLabel()
        self.mentions_label.setWordWrap(True)
        self.empty_label = QLabel("No market statistics yet: refresh them from Synergy Research Group.")
        self.empty_label.setObjectName("muted")
        self.refresh_button = QPushButton("\u27f3  Refresh from Synergy")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self._build_layout()
        self.panel.perimeter_changed.connect(self._update_charts)
        self.set_statistics(None)

    ############################
    # Internal Helpers Methods #
    ############################

    def _title(self, text: str) -> QLabel:
        """Build a chart title.

        Args:
            text (str): The title.

        Returns:
            QLabel: The title label.
        """
        label = QLabel(text.upper())
        label.setObjectName("muted")
        return label

    def _build_layout(self) -> None:
        """Lay the perimeter panel out on the left and the charts on the right, in a scrollable column."""
        header = QHBoxLayout()
        title = QLabel("Cloud market shares")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.refresh_button)
        charts = QWidget()
        column = QVBoxLayout(charts)
        column.setSpacing(10)
        column.addLayout(header)
        column.addWidget(self.source_label)
        column.addWidget(self.empty_label)
        for text, widget in (
            ("Market shares of the latest selected period", self.share_chart),
            ("Market share trend", self.trend_chart),
            ("Market size", self.size_chart),
        ):
            column.addWidget(self._title(text))
            column.addWidget(widget)
        column.addWidget(self.mentions_label)
        column.addStretch(1)
        area = QScrollArea()
        area.setWidget(charts)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.panel)
        layout.addWidget(area, 1)

    def _selected_reports(self) -> List[MarketReport]:
        """Get the reports within the checked regions, segments and periods.

        Returns:
            List[MarketReport]: The reports, in chronological order.
        """
        if self.statistics is None:
            return []
        regions, segments, periods = self.panel.regions(), self.panel.segments(), self.panel.periods()
        reports = [
            report
            for report in self.statistics.reports
            if report.region in regions and report.segment in segments and report.period in periods
        ]
        return sorted(reports, key=lambda report: report.sort_key())

    def _groups(self, reports: List[MarketReport]) -> Dict[GroupKey, List[MarketReport]]:
        """Group reports by region and segment.

        Args:
            reports (List[MarketReport]): The reports, in chronological order.

        Returns:
            Dict[GroupKey, List[MarketReport]]: The reports of each region and segment, in region then segment order,
                each in chronological order.
        """
        groups: Dict[GroupKey, List[MarketReport]] = {}
        for report in reports:
            groups.setdefault((report.region, report.segment), []).append(report)
        regions, segments = list(MarketRegion), list(MarketSegment)
        order = sorted(groups, key=lambda key: (regions.index(key[0]), segments.index(key[1])))
        return {key: groups[key] for key in order}

    def _bar(self, report: MarketReport, player: MarketPlayer) -> Optional[ShareBar]:
        """Build the bar of a player in a report.

        Args:
            report (MarketReport): The report.
            player (MarketPlayer): The player.

        Returns:
            Optional[ShareBar]: The bar, `None` when the report gives no share of the player.
        """
        share = report.share_of(player)
        if share is None:
            return None
        return ShareBar(
            label=self.theme.player_label(player),
            share_pct=share.share_pct,
            color=self.theme.player_color(player),
            low_pct=share.share_low_pct,
            high_pct=share.share_high_pct,
            approximate=share.approximate,
            computed=share.computed,
        )

    def _share_groups(self, groups: Dict[GroupKey, List[MarketReport]]) -> List[ShareGroup]:
        """Build the bar groups of the latest report of each region and segment.

        Args:
            groups (Dict[GroupKey, List[MarketReport]]): The reports of each region and segment.

        Returns:
            List[ShareGroup]: The title and the bars of each group having a share of a checked player.
        """
        bar_groups: List[ShareGroup] = []
        for (region, segment), reports in groups.items():
            latest = reports[-1]
            bars = [bar for player in self.panel.players() if (bar := self._bar(latest, player)) is not None]
            if bars:
                title = f"{self.theme.REGION_LABELS[region]} · {self.theme.SEGMENT_LABELS[segment]}"
                bar_groups.append((f"{title} · {latest.period}", bars))
        return bar_groups

    def _value(self, report: Optional[MarketReport], player: MarketPlayer) -> Optional[float]:
        """Get the share of a player in a report, if any.

        Args:
            report (Optional[MarketReport]): The report, `None` when the period has none.
            player (MarketPlayer): The player.

        Returns:
            Optional[float]: The share, in percent, `None` when unknown.
        """
        share = report.share_of(player) if report is not None else None
        return share.share_pct if share is not None else None

    def _trend(self, groups: Dict[GroupKey, List[MarketReport]]) -> Tuple[List[str], List[TrendSeries], List[str]]:
        """Build the trend lines: one per region, segment and checked player having shares, a line style per group.

        Args:
            groups (Dict[GroupKey, List[MarketReport]]): The reports of each region and segment.

        Returns:
            Tuple[List[str], List[TrendSeries], List[str]]: The periods of the x axis, the lines and the periods
                starting a methodology break.
        """
        keys = {report.period: report.sort_key() for reports in groups.values() for report in reports}
        periods = sorted(keys, key=lambda period: keys[period])
        several = len(groups) > 1
        series: List[TrendSeries] = []
        for group, ((region, segment), reports) in enumerate(groups.items()):
            style = self.LINE_STYLES[group % len(self.LINE_STYLES)]
            by_period = {report.period: report for report in reports}
            for player in self.panel.players():
                values = [self._value(by_period.get(period), player) for period in periods]
                if any(value is not None for value in values):
                    label = self.theme.player_label(player)
                    if several:
                        label = f"{label} \u00b7 {self.REGION_TAGS[region]}"
                        if len({key[1] for key in groups}) > 1:
                            label = f"{label} \u00b7 {self.SEGMENT_TAGS[segment]}"
                    series.append((label, self.theme.player_color(player), values, style))
        breaks = [report.period for reports in groups.values() for report in reports if report.methodology_break]
        return periods, series, breaks

    def _sizes(self, reports: List[MarketReport]) -> List[SizeBar]:
        """Build the market size bars of the reports giving a market size.

        Args:
            reports (List[MarketReport]): The reports, in chronological order.

        Returns:
            List[SizeBar]: The label, size, currency and growth of each bar.
        """
        regions = {report.region for report in reports}
        bars: List[SizeBar] = []
        for report in reports:
            if report.market_size_bn is None:
                continue
            label = report.period if len(regions) == 1 else f"{report.period} {self.REGION_TAGS[report.region]}"
            bars.append((label, report.market_size_bn, report.currency, report.growth_pct))
        return bars

    def _mentions(self, groups: Dict[GroupKey, List[MarketReport]]) -> str:
        """Describe the providers named without a share in the latest report of each group.

        Args:
            groups (Dict[GroupKey, List[MarketReport]]): The reports of each region and segment.

        Returns:
            str: The providers, ranked first, or an empty text when none is named.
        """
        names: Dict[str, Optional[int]] = {}
        for reports in groups.values():
            for mention in reports[-1].mentions:
                if names.get(mention.name) is None:
                    names[mention.name] = mention.rank
        if not names:
            return ""
        ordered = sorted(names.items(), key=lambda item: (item[1] is None, item[1] or 0, item[0]))
        listed = ", ".join(f"{rank}. {name}" if rank else name for name, rank in ordered)
        return f"Not quantified by {self.statistics.source if self.statistics else 'the source'}: {listed}."

    def _source(self, reports: List[MarketReport]) -> str:
        """Describe the source of the latest selected report, linking to its article.

        Args:
            reports (List[MarketReport]): The reports, in chronological order.

        Returns:
            str: The rich text source line, empty when no report is selected.
        """
        if not reports or self.statistics is None:
            return ""
        latest = max(reports, key=lambda report: (report.published, report.sort_key()))
        link = f'<a href="{html.escape(latest.source_url, quote=True)}">{html.escape(latest.title)}</a>'
        crawled = self.statistics.crawled_at.astimezone().strftime("%d %b %Y")
        source = html.escape(self.statistics.source)
        return f"Source: {source}, {link} ({latest.published:%d %b %Y}). Crawled on {crawled}."

    def _update_charts(self) -> None:
        """Show the charts of the checked perimeter."""
        reports = self._selected_reports()
        groups = self._groups(reports)
        self.share_chart.set_groups(self._share_groups(groups))
        self.trend_chart.set_series(*self._trend(groups))
        self.size_chart.set_bars(self._sizes(reports))
        self.mentions_label.setText(self._mentions(groups))
        self.source_label.setText(self._source(reports))
        self.logger.debug("Statistics charts updated: %d reports in the perimeter.", len(reports))

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_statistics(self, statistics: Optional[MarketStatistics]) -> None:
        """Show statistics, keeping the perimeter choices.

        Args:
            statistics (Optional[MarketStatistics]): The statistics, `None` when never crawled.
        """
        self.statistics = statistics
        self.empty_label.setVisible(statistics is None or not statistics.reports)
        self.panel.set_reports(statistics.reports if statistics else [])
