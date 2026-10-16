from __future__ import annotations

from typing import Tuple
from unittest.mock import patch

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from gui.flags.flag_design import FlagDesign
from gui.flags.flag_painter import FlagPainter
from models.cloud.enums import Country


@pytest.mark.parametrize(
    ("country", "height", "pixel", "color"),
    [
        (Country.FRANCE, 20, (4, 10), "#002395"),
        (Country.FRANCE, 20, (15, 10), "#ffffff"),
        (Country.FRANCE, 20, (25, 10), "#ed2939"),
        (Country.BELGIUM, 20, (15, 10), "#fae042"),
        (Country.ITALY, 20, (4, 10), "#009246"),
        (Country.GERMANY, 20, (15, 3), "#000000"),
        (Country.GERMANY, 20, (15, 10), "#dd0000"),
        (Country.GERMANY, 20, (15, 16), "#ffce00"),
        (Country.LUXEMBOURG, 20, (15, 16), "#00a1de"),
        (Country.SPAIN, 20, (15, 2), "#aa151b"),
        (Country.SPAIN, 20, (15, 10), "#f1bf00"),
        (Country.SWITZERLAND, 20, (15, 10), "#ffffff"),
        (Country.SWITZERLAND, 20, (3, 3), "#da291c"),
        (Country.SWITZERLAND, 20, (15, 2), "#da291c"),
        (Country.UNITED_KINGDOM, 20, (9, 1), "#012169"),
        (Country.UNITED_KINGDOM, 20, (3, 10), "#c8102e"),
        (Country.UNITED_KINGDOM, 20, (3, 7), "#ffffff"),
        (Country.UNITED_STATES, 26, (5, 5), "#3c3b6e"),
        (Country.UNITED_STATES, 26, (30, 1), "#b22234"),
        (Country.UNITED_STATES, 26, (30, 3), "#ffffff"),
        (Country.CHINA, 20, (5, 5), "#ffff00"),
        (Country.CHINA, 20, (25, 15), "#ee1c25"),
    ],
)
def test_flag_colours(qapp: QApplication, country: Country, height: int, pixel: Tuple[int, int], color: str) -> None:
    image = FlagPainter().pixmap(country, height).toImage()

    assert image.pixelColor(*pixel) == QColor(color)


@pytest.mark.parametrize("country", list(Country))
def test_every_country_has_a_flag(qapp: QApplication, country: Country) -> None:
    pixmap = FlagPainter().pixmap(country, 20)

    assert (pixmap.width(), pixmap.height()) == (30, 20)
    assert pixmap.toImage().pixelColor(0, 0).alpha() > 0


def test_flags_are_drawn_once_per_height(qapp: QApplication) -> None:
    painter = FlagPainter()

    first = painter.pixmap(Country.FRANCE)

    assert painter.pixmap(Country.FRANCE) is first
    assert painter.pixmap(Country.FRANCE, 24) is not first
    assert set(painter.pixmaps) == {(Country.FRANCE, 12), (Country.FRANCE, 24)}
    assert not painter.icon(Country.FRANCE).isNull()


def test_unequal_band_weights_fall_back_to_equal_bands(qapp: QApplication) -> None:
    design = FlagDesign(bands=["#000000", "#ffffff"], weights=[1])

    with patch.dict(FlagPainter.DESIGNS, {Country.FRANCE: design}):
        image = FlagPainter().pixmap(Country.FRANCE, 20).toImage()

    assert image.pixelColor(15, 5) == QColor("#000000")
    assert image.pixelColor(15, 15) == QColor("#ffffff")


def test_design_is_frozen() -> None:
    design = FlagDesign(bands=["#000000"])

    with pytest.raises(ValueError, match="frozen"):
        design.vertical = True  # type: ignore[misc]
