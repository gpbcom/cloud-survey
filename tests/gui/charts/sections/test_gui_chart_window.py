from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from gui.charts.sections.chart_state_store import ChartStateStore
from gui.charts.sections.section.chart_section import ChartSection


def section(qtbot: QtBot, detachable: bool = True) -> ChartSection:
    card = ChartSection("tests/chart", "Market shares", QLabel("chart"), ChartStateStore(), detachable=detachable)
    qtbot.addWidget(card)
    card.show()
    return card


def test_widen_opens_the_chart_in_a_window_closed_by_escape(qtbot: QtBot) -> None:
    card = section(qtbot)
    assert card.widen_button is not None

    card.widen_button.click()

    window = card.chart_window
    assert window is not None
    assert window.isVisible()
    assert card.body.parent() is window
    assert card.placeholder.isVisible()
    assert window.windowTitle() == "Market shares"
    assert card.open_window() is window
    qtbot.keyClick(window, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: card.chart_window is None)
    assert card.body.parent() is card
    assert card.body.isVisible()
    assert not card.placeholder.isVisible()


def test_the_cross_closes_the_window(qtbot: QtBot) -> None:
    card = section(qtbot)
    window = card.open_window()
    assert window is not None

    window.close_button.click()

    qtbot.waitUntil(lambda: card.chart_window is None)
    assert card.body.parent() is card


def test_tables_and_controls_stay_in_their_card(qtbot: QtBot) -> None:
    card = section(qtbot, detachable=False)

    assert card.widen_button is None
    assert card.open_window() is None
