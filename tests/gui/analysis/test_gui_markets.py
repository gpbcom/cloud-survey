from __future__ import annotations

from datetime import date
from typing import List
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from pytestqt.qtbot import QtBot

from gui.analysis.markets.charts.lag_chart import LagChart
from gui.analysis.markets.charts.time_series_chart import TimeSeriesChart
from gui.analysis.markets.markets_panel import MarketsPanel
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.history.chronology import Chronology
from models.markets.charts.chart_dot import ChartDot
from models.markets.charts.chart_line import ChartLine
from models.markets.correlation.counterpart import Counterpart
from models.markets.enums import (
    CorrelationCounterpart,
    Device,
    MarketFeed,
    PriceScale,
    ShareMetric,
    ShareSource,
    StockView,
)
from models.markets.facts.price_point import PricePoint
from models.markets.markets_catalog import MarketsCatalog
from models.markets.series.lag_correlation import LagCorrelation
from models.markets.series.share_series import ShareSeries
from models.markets.series.stock_series import StockSeries
from models.markets.values.market_share_value import MarketShareValue
from storage.storage import Storage


def panel(qtbot: QtBot, catalog: MarketsCatalog, chronology: Chronology) -> MarketsPanel:
    built = MarketsPanel(Theme(), MagicMock(), catalog, chronology)
    for body in (built.share_body, built.stock_body, built.correlation_body):
        qtbot.addWidget(body)
        body.resize(1200, 520)
        body.show()
    return built


def months(count: int, start: float = 60.0) -> List[tuple[date, float]]:
    return [(date(2010 + index // 12, index % 12 + 1, 1), start + index * 0.1) for index in range(count)]


class TestTimeSeriesChart:
    def test_lines_dots_markers_and_legend(self, qtbot: QtBot, markets_chronology: Chronology) -> None:
        chart = TimeSeriesChart(Theme())
        qtbot.addWidget(chart)
        chart.resize(1000, 420)
        chart.set_data(
            [
                ChartLine(key="google", label="Google", color="#34a853", points=months(60)),
                ChartLine(key="others", label="Others", color="#9aa4b2", points=months(60, 10.0), note="Linux"),
            ],
            [ChartDot(day=date(2012, 6, 1), value=40.0, color="#7e57c2", label="DEC: to Compaq", tooltip="8-K")],
            "%",
            False,
            True,
            "search/ww/all",
        )
        chart.set_events(markets_chronology.events, markets_chronology)
        chart.show()
        chart.grab()

        assert [key for _, key in chart.legend] == ["google", "others"]
        assert len(chart.dot_hits) == 1
        assert all(2010 <= event.when() <= 2015 for _, _, event in chart.markers.hits)
        frame = chart.zoom.frame
        assert frame is not None
        hover = chart._hover_text(QPointF(frame.map_x(2012.0), frame.area.center().y()))
        assert hover is not None
        assert hover.index("Google") < hover.index("Others"), "the highest value first"
        assert "%" in hover

    def test_a_legend_click_hides_its_line(self, qtbot: QtBot) -> None:
        chart = TimeSeriesChart(Theme())
        qtbot.addWidget(chart)
        chart.resize(900, 400)
        chart.set_data([ChartLine(key="a", label="A", color="#ff0000", points=months(24))], [], "USD", True, False, "k")
        chart.show()
        chart.grab()

        qtbot.mouseClick(chart, Qt.MouseButton.LeftButton, pos=chart.legend[0][0].center().toPoint())

        assert chart.hidden == {"a"}
        assert chart._shown() == []

    def test_a_line_breaks_only_where_its_points_are_unusually_far_apart(self, qtbot: QtBot) -> None:
        chart = TimeSeriesChart(Theme())
        qtbot.addWidget(chart)
        chart.resize(900, 400)
        quarters = [(date(2010 + index // 4, index % 4 * 3 + 1, 1), 30.0) for index in range(8)]
        named_twice = [(date(2011, 7, 1), 20.0), (date(2019, 4, 1), 28.0)]
        chart.set_data(
            [
                ChartLine(key="samsung", label="Samsung", color="#ff0000", dots=True, points=quarters),
                ChartLine(key="sk-hynix", label="SK hynix", color="#00ff00", dots=True, points=named_twice),
            ],
            [],
            "%",
            False,
            True,
            "dram",
        )
        chart.show()
        chart.grab()
        quarterly = chart._gap_days()
        chart.set_data(
            [
                ChartLine(
                    key="ibm", label="IBM", color="#0000ff", points=[(date(1961 + y, 1, 1), 70.0) for y in range(5)]
                )
            ],
            [],
            "%",
            False,
            True,
            "mainframes",
        )
        yearly = chart._gap_days()

        assert 2 * 92 < quarterly < 365, "a line named in releases years apart is broken, a missed quarter is not"
        assert yearly > 365, "consecutive years stay joined"

    def test_the_rate_of_change_replaces_the_values_and_back(self, qtbot: QtBot) -> None:
        chart = TimeSeriesChart(Theme())
        qtbot.addWidget(chart)
        chart.resize(900, 400)
        points = [(date(2020, 1, 1), 10.0), (date(2021, 1, 1), 14.0), (date(2022, 1, 1), 12.0)]
        dot = ChartDot(day=date(2020, 6, 1), value=40.0, color="#7e57c2", label="IPO", tooltip="S-1")
        chart.set_data([ChartLine(key="a", label="A", color="#ff0000", points=points)], [dot], "%", True, True, "k")

        chart.set_derivative(True)
        chart.grab()
        derived = chart.lines[0].points

        assert [day for day, _ in derived] == [date(2021, 1, 1), date(2022, 1, 1)]
        assert derived[0][1] == pytest.approx(4.0, rel=0.01)
        assert derived[1][1] == pytest.approx(-2.0, rel=0.01)
        assert (chart.unit, chart.log_y, chart.floor_zero, chart.dots) == ("pts/yr", False, False, [])
        chart.set_derivative(False)
        assert (chart.lines[0].points, chart.unit, chart.log_y, len(chart.dots)) == (points, "%", True, 1)

    def test_lone_values_say_why_nothing_is_derived(self, qtbot: QtBot) -> None:
        chart = TimeSeriesChart(Theme())
        dot = ChartDot(day=date(2020, 6, 1), value=40.0, color="#7e57c2", label="IPO", tooltip="S-1")
        chart.set_data([], [dot], "USD bn", True, False, "k")

        chart.set_derivative(True)

        assert chart.message.startswith("No line to derive")

    def test_without_data_the_message_shows(self, qtbot: QtBot) -> None:
        chart = TimeSeriesChart(Theme())
        qtbot.addWidget(chart)
        chart.set_message("Nothing stored.")
        chart.grab()

        assert chart.zoom.frame is None or chart.lines == []
        assert chart.message == "Nothing stored."


class TestMarketsPanel:
    def test_share_lines_take_their_company_colour_and_fill_the_correlation_picker(
        self, qtbot: QtBot, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        built = panel(qtbot, markets_catalog, markets_chronology)
        query = built._share_query()
        series = [
            ShareSeries(company="google", label="Google", labels=["Google"], points=months(40)),
            ShareSeries(company="duckduckgo", label="DuckDuckGo", points=months(40, 1.0)),
            ShareSeries(label="Others", points=months(40, 5.0)),
        ]
        built.generations["shares"] = 1

        built._on_shares(1, query, series)

        lines = built.share_chart.lines
        assert [line.key for line in lines] == ["google", "duckduckgo", "others"]
        assert lines[0].color == Theme().company_color(markets_chronology.company("google")).name()  # type: ignore[arg-type]
        assert [built.company_box.itemData(index) for index in range(built.company_box.count())] == [
            "google",
            "duckduckgo",
        ], "every company drawn: a company without listing can still be correlated with another series"
        assert "StatCounter" in built.share_note.text()

    def test_a_late_answer_is_dropped(
        self, qtbot: QtBot, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        built = panel(qtbot, markets_catalog, markets_chronology)
        built.generations["shares"] = 2

        built._on_shares(1, built._share_query(), [ShareSeries(label="Others", points=months(3))])

        assert built.share_chart.lines == []

    def test_stock_lines_and_valuation_dots(
        self, qtbot: QtBot, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        built = panel(qtbot, markets_catalog, markets_chronology)
        series = [
            StockSeries(
                key="TPE:2330", company="tsmc", label="TSMC (TPE:2330)", currency="index", points=months(30, 100.0)
            ),
            StockSeries(
                key="NYSE:TSM",
                company="tsmc",
                label="TSMC (NYSE:TSM)",
                currency="index",
                primary=False,
                points=months(30, 100.0),
            ),
        ]
        built.generations["stocks"] = 1

        built._on_stocks(1, (StockView.LISTINGS, ("tsmc",), "USD", PriceScale.INDEXED, True), series)
        dashed = [line.dashed for line in built.stock_chart.lines]
        built._on_stocks(1, (StockView.VALUATIONS, (), "USD", PriceScale.LOG, False), [])

        assert dashed == [False, True]
        assert built.stock_chart.unit == "USD bn"
        assert len(built.stock_chart.dots) == len(markets_catalog.valuations)
        assert built.stock_chart.log_y

    def test_a_leader_band_opens_its_segment_and_company(
        self, qtbot: QtBot, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        built = panel(qtbot, markets_catalog, markets_chronology)
        reign = next(
            reign for reign in markets_chronology.reigns if reign.segment == "mobile" and reign.company == "google"
        )

        assert built.focus_reign(reign.key())
        segment, _, device, _ = built.share_controls.query()
        assert segment.key == "operating-systems"
        assert device is Device.MOBILE
        assert built.stock_controls.companies() == ["google"]
        assert not built.focus_reign("event:x")

    def test_the_area_picker_shows_flags(
        self, qtbot: QtBot, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        built = panel(qtbot, markets_catalog, markets_chronology)
        box = built.share_controls.area_box

        texts = {str(box.itemData(index)): box.itemText(index) for index in range(box.count())}

        assert texts["FR"].startswith(chr(0x1F1EB) + chr(0x1F1F7))
        assert texts["ww"].startswith(chr(0x1F310))
        assert texts["eu27"].endswith("(estimate)")


class TestLagChart:
    def test_bars_and_their_tooltips(self, qtbot: QtBot) -> None:
        chart = LagChart(Theme())
        qtbot.addWidget(chart)
        chart.resize(800, 260)
        lags = [
            LagCorrelation(
                lag=lag, rho=0.1 * lag, low=0.1 * lag - 0.1, high=0.1 * lag + 0.1, p_value=0.01, q_value=0.02, months=80
            )
            for lag in range(-3, 4)
        ]
        chart.set_lags(lags)
        chart.show()
        chart.grab()

        assert len(chart.bars) == 7
        assert "Lag +2 months" in chart._tooltip(lags[5])
        assert "too few" in chart._tooltip(LagCorrelation(lag=1, months=3))


@pytest.mark.db
class TestMarketsOnTheDatabase:
    async def test_the_cards_read_the_stored_crawls(
        self,
        qtbot: QtBot,
        storage: Storage,
        gui_loop: StorageLoop,
        markets_catalog: MarketsCatalog,
        markets_chronology: Chronology,
    ) -> None:
        await storage.shares.upsert(
            [
                MarketShareValue(
                    segment="search",
                    area="ww",
                    period=day,
                    metric=ShareMetric.USAGE,
                    device=Device.ALL,
                    source=ShareSource.STATCOUNTER,
                    label=label,
                    company=company,
                    value=value * weight,
                )
                for day, value in months(48)
                for label, company, weight in (("Google", "google", 1.0), ("bing", "microsoft", 0.1))
            ]
            + [
                MarketShareValue(
                    segment="browsers",
                    area="ww",
                    period=day,
                    metric=ShareMetric.USAGE,
                    device=Device.ALL,
                    source=ShareSource.STATCOUNTER,
                    label="Chrome",
                    company="google",
                    value=value / 2 + (index % 5),
                )
                for index, (day, value) in enumerate(months(48))
            ]
        )
        await storage.stocks.upsert(
            [
                PricePoint(listing="NASDAQ:GOOGL", day=day.replace(day=25), close=value, currency="USD", source_url="u")
                for day, value in months(48)
            ],
            MarketFeed.GOOGLE_FINANCE,
        )
        built = MarketsPanel(Theme(), gui_loop, markets_catalog, markets_chronology)
        qtbot.addWidget(built.share_body)
        qtbot.addWidget(built.stock_body)
        qtbot.addWidget(built.correlation_body)

        built.refresh()

        qtbot.waitUntil(lambda: len(built.share_chart.lines) == 2, timeout=10_000)
        qtbot.waitUntil(lambda: bool(built.stock_chart.lines), timeout=10_000)
        assert [line.key for line in built.stock_chart.lines] == ["NASDAQ:GOOGL"]
        qtbot.waitUntil(lambda: built.correlation_controls.counterpart() is not None, timeout=10_000)
        offered = built.correlation_controls.counterparts
        assert [(entry.kind, entry.label) for entry in offered[:2]] == [
            (CorrelationCounterpart.STOCK, "NASDAQ:GOOGL stock"),
            (CorrelationCounterpart.SHARE, "Web browsers / Worldwide / statcounter"),
        ]
        assert [entry.segment for entry in offered[2:]] == ["foundry", "dram", "nand"], "no home currency in USD"
        built.correlate()
        qtbot.waitUntil(lambda: built.correlate_button.isEnabled(), timeout=10_000)
        assert "share changes lead the returns" in built.correlation_summary.text()
        built.correlation_controls.against_box.setCurrentIndex(1)
        built.correlate()
        qtbot.waitUntil(lambda: "Web browsers" in built.correlation_summary.text(), timeout=10_000)
        assert (
            "against Web browsers / Worldwide / statcounter: up to 47 months paired" in built.correlation_summary.text()
        )
        assert "the Web browsers / Worldwide / statcounter changes" in built.lag_chart.counterpart

    async def test_manual_points_fill_only_the_periods_the_source_leaves_empty(
        self, storage: Storage, gui_loop: StorageLoop, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        def value(source: ShareSource, period: date, share: float) -> MarketShareValue:
            return MarketShareValue(
                segment="pcs",
                area="ww",
                period=period,
                granularity="year" if source is ShareSource.MANUAL else "quarter",
                metric=ShareMetric.UNITS,
                source=source,
                label="Lenovo",
                company="lenovo",
                value=share,
            )

        await storage.shares.upsert(
            [
                value(ShareSource.IDC, date(2025, 1, 1), 24.0),
                value(ShareSource.MANUAL, date(2025, 1, 1), 27.2),
                value(ShareSource.MANUAL, date(1984, 1, 1), 26.0),
            ]
        )
        built = MarketsPanel(Theme(), gui_loop, markets_catalog, markets_chronology)

        lines = await built._read_shares(("pcs", "ww", Device.ALL, ShareSource.IDC, 8), storage)

        assert dict(lines[0].points) == {date(1984, 1, 1): 26.0, date(2025, 1, 1): 24.0}


class TestMarketsTooltips:
    def test_every_control_and_choice_explains_itself(
        self, qtbot: QtBot, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        built = panel(qtbot, markets_catalog, markets_chronology)
        shares, stocks = built.share_controls, built.stock_controls
        boxes = [
            shares.segment_box,
            shares.area_box,
            shares.device_box,
            stocks.view_box,
            stocks.currency_box,
            stocks.scale_box,
        ]

        missing = [
            (box.itemText(index), box.toolTip()[:20])
            for box in boxes
            for index in range(box.count())
            if len(str(box.itemData(index, Qt.ItemDataRole.ToolTipRole) or "")) < 60
        ]

        assert missing == []
        for widget in (
            *boxes,
            shares.top_box,
            shares.derivative_box,
            stocks.companies_button,
            stocks.secondary_box,
            stocks.derivative_box,
            built.company_box,
        ):
            assert widget.toolTip().startswith("<qt>")
        eu27 = str(shares.area_box.itemData(shares.area_box.findData("eu27"), Qt.ItemDataRole.ToolTipRole))
        assert "internet users" in eu27
        assert "27 member states" in eu27
        shares.derivative_box.setChecked(True)
        stocks.derivative_box.setChecked(True)
        assert built.share_chart.derivative
        assert built.stock_chart.derivative

    def test_the_correlate_tooltip_follows_the_counterpart(
        self, qtbot: QtBot, markets_catalog: MarketsCatalog, markets_chronology: Chronology
    ) -> None:
        built = panel(qtbot, markets_catalog, markets_chronology)
        controls = built.correlation_controls
        controls.set_companies(["google"], {"google": "Google"})
        controls.set_counterparts(
            [
                Counterpart(kind=CorrelationCounterpart.STOCK, label="NASDAQ:GOOGL stock", listing="NASDAQ:GOOGL"),
                Counterpart(
                    kind=CorrelationCounterpart.CONTEXT,
                    label="DRAM concentration (HHI)",
                    segment="dram",
                    source=ShareSource.TRENDFORCE,
                ),
            ]
        )

        monthly = built.correlate_button.toolTip()
        controls.against_box.setCurrentIndex(1)
        quarterly = built.correlate_button.toolTip()

        assert "Google&#x27;s share of Web search" in monthly
        assert "NASDAQ:GOOGL stock" in monthly
        assert "-12 to +12 months" in monthly
        assert "400 resamples" in monthly
        assert "-4 to +4 quarters" in quarterly
        assert "HHI" in quarterly
        assert "Google" in str(controls.company_box.itemData(0, Qt.ItemDataRole.ToolTipRole))
        assert all(
            len(str(controls.against_box.itemData(index, Qt.ItemDataRole.ToolTipRole))) > 60 for index in range(2)
        )
