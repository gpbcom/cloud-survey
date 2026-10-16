from __future__ import annotations

import logging

import pytest
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from gui.theme import Theme
from models.cloud.enums import CloudProvider, Country


@pytest.mark.parametrize("provider", list(CloudProvider))
def test_every_provider_has_a_colour_and_labels(provider: CloudProvider) -> None:
    theme = Theme()

    assert theme.provider_color(provider) == QColor(Theme.PROVIDER_COLORS[provider])
    assert theme.provider_color(provider).isValid()
    assert theme.provider_label(provider) == Theme.PROVIDER_LABELS[provider]
    assert Theme.PROVIDER_SHORT_LABELS[provider]


def test_provider_colours_are_distinct() -> None:
    assert len(set(Theme.PROVIDER_COLORS.values())) == len(CloudProvider)


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (logging.DEBUG, logging.DEBUG),
        (logging.INFO, logging.INFO),
        (25, logging.INFO),
        (logging.WARNING, logging.WARNING),
        (logging.ERROR, logging.ERROR),
        (logging.CRITICAL, logging.CRITICAL),
        (5, logging.DEBUG),
    ],
)
def test_level_colours(level: int, expected: int) -> None:
    assert Theme().level_color(level) == Theme.LEVEL_COLORS[expected]


def test_icons(qapp: QApplication) -> None:
    theme = Theme()

    icon = theme.provider_icon(CloudProvider.AWS)

    assert not icon.isNull()
    image = icon.pixmap(14, 14).toImage()
    assert image.pixelColor(7, 7) == QColor(Theme.PROVIDER_COLORS[CloudProvider.AWS])
    assert image.pixelColor(0, 0).alpha() == 0


def test_stylesheet_uses_the_palette() -> None:
    stylesheet = Theme().stylesheet()

    for color in (Theme.WINDOW, Theme.SURFACE, Theme.ACCENT, Theme.TEXT_MUTED):
        assert color in stylesheet


def test_apply(qapp: QApplication) -> None:
    previous_stylesheet, previous_palette = qapp.styleSheet(), qapp.palette()
    try:
        Theme().apply(qapp)

        assert qapp.styleSheet() == Theme().stylesheet()
        assert qapp.palette().color(QPalette.ColorRole.Window) == QColor(Theme.WINDOW)
    finally:
        qapp.setStyleSheet(previous_stylesheet)
        qapp.setPalette(previous_palette)


@pytest.mark.parametrize("country", list(Country))
def test_every_country_has_a_label_and_a_flag(country: Country, qapp: QApplication) -> None:
    theme = Theme()

    assert theme.country_label(country)
    assert not theme.flag_icon(country).isNull()
    assert theme.flag_pixmap(country, 20).size().height() == 20


def test_country_labels() -> None:
    assert Theme().country_label(Country.UNITED_KINGDOM) == "United Kingdom"
    assert set(Theme.COUNTRY_LABELS) == set(Country)
