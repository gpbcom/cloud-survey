from __future__ import annotations

from typing import List
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QAction, QMouseEvent
from PyQt6.QtWidgets import QLabel, QWidgetAction
from pytestqt.qtbot import QtBot

from gui.theme import Theme
from gui.widgets.marketplace_menu import MarketplaceMenu
from models.cloud.enums import CloudProvider

PROVIDERS = [CloudProvider.AWS, CloudProvider.AZURE, CloudProvider.STACKIT, CloudProvider.CIVO]


@pytest.fixture
def menu(qtbot: QtBot) -> MarketplaceMenu:
    widget = MarketplaceMenu(Theme(), PROVIDERS)
    qtbot.addWidget(widget)
    return widget


def texts(menu: MarketplaceMenu) -> List[str]:
    return [action.text() for action in menu.actions() if not action.isSeparator()]


def release_on(menu: MarketplaceMenu, action: QAction) -> None:
    point = QPointF(menu.actionGeometry(action).center())
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        point,
        point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    menu.mouseReleaseEvent(event)


def test_marketplaces_are_grouped_by_country(menu: MarketplaceMenu) -> None:
    assert menu.title() == "&Marketplaces"
    assert texts(menu) == [
        "Select all",
        "Select none",
        "United States",
        "Amazon Web Services",
        "Microsoft Azure",
        "Germany",
        "STACKIT",
        "United Kingdom",
        "Civo",
        "▶  Extract the 0 selected marketplaces",
    ]
    (header,) = [action for action in menu.actions() if action.text() == "Germany"]
    assert isinstance(header, QWidgetAction)
    widget = header.defaultWidget()
    assert widget is not None
    flag, name = widget.findChildren(QLabel)
    pixmap = flag.pixmap()
    assert pixmap is not None
    assert not pixmap.isNull()
    assert (name.text(), name.font().bold()) == ("Germany", True)
    assert not header.isCheckable()
    assert not menu.extract_action.isEnabled()


def test_selection(menu: MarketplaceMenu) -> None:
    menu.provider_actions[CloudProvider.CIVO].setChecked(True)

    assert menu.selected_providers() == [CloudProvider.CIVO]
    assert menu.extract_action.text() == "▶  Extract the 1 selected marketplace"
    assert menu.extract_action.isEnabled()

    menu.select_all_action.trigger()
    assert menu.selected_providers() == PROVIDERS
    assert menu.extract_action.text() == "▶  Extract the 4 selected marketplaces"

    menu.select_none_action.trigger()
    assert menu.selected_providers() == []

    menu.select([CloudProvider.AZURE, CloudProvider.STACKIT])
    assert menu.selected_providers() == [CloudProvider.AZURE, CloudProvider.STACKIT]


def test_extraction_request(menu: MarketplaceMenu, qtbot: QtBot) -> None:
    menu.select([CloudProvider.STACKIT, CloudProvider.AWS])

    with qtbot.waitSignal(menu.extract_requested) as signal:
        menu.extract_action.trigger()

    assert signal.args == [["amazon-web-services", "stackit"]]


def test_counts(menu: MarketplaceMenu) -> None:
    menu.set_counts({CloudProvider.AWS: 18343})

    aws = menu.provider_actions[CloudProvider.AWS]
    civo = menu.provider_actions[CloudProvider.CIVO]
    assert (aws.text(), aws.toolTip()) == ("Amazon Web Services  (18,343)", "18,343 software in the last extraction")
    assert (civo.text(), civo.toolTip()) == ("Civo", "Not extracted yet")

    menu.set_counts({})
    assert aws.text() == "Amazon Web Services"


def test_checking_a_marketplace_keeps_the_menu_open(menu: MarketplaceMenu, qtbot: QtBot) -> None:
    menu.popup(menu.mapToGlobal(menu.rect().topLeft()))
    qtbot.waitExposed(menu)
    action = menu.provider_actions[CloudProvider.AZURE]

    release_on(menu, action)

    assert action.isChecked()
    assert menu.isVisible()


def test_other_entries_behave_normally(menu: MarketplaceMenu, qtbot: QtBot) -> None:
    menu.popup(menu.mapToGlobal(menu.rect().topLeft()))
    qtbot.waitExposed(menu)

    with patch("gui.widgets.marketplace_menu.QMenu.mouseReleaseEvent") as default:
        release_on(menu, menu.select_all_action)
        menu.mouseReleaseEvent(None)

    assert default.call_count == 2
