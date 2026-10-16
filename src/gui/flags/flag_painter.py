from __future__ import annotations

# Standard Library Imports.
import math
from logging import Logger, getLogger
from typing import ClassVar, Dict, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

# First Party Imports.
from gui.flags.flag_design import FlagDesign
from models.cloud.enums import Country


class FlagPainter:
    """Draw the national flags of the cloud provider countries, as cached pixmaps and icons.

    The flags are painted rather than taken from an emoji font, so that they look the same on every system.

    Attributes:
        RATIO (ClassVar[float]): The width to height ratio of the flags.
        BORDER (ClassVar[QColor]): The thin border colour, keeping the dark flag colours visible on the dark theme.
        STARS (ClassVar[Tuple[Tuple[float, float, float], ...]]): The centre and radius of the stars, in a 30 x 20
            grid: the large star first.
        DESIGNS (ClassVar[Dict[Country, FlagDesign]]): The design of each country flag.
        pixmaps (Dict[Tuple[Country, int], QPixmap]): The flags already drawn, by country and height.
    """

    RATIO: ClassVar[float] = 1.5
    BORDER: ClassVar[QColor] = QColor(255, 255, 255, 90)
    STARS: ClassVar[Tuple[Tuple[float, float, float], ...]] = (
        (5.0, 5.0, 3.0),
        (10.0, 2.0, 1.0),
        (12.0, 4.0, 1.0),
        (12.0, 7.0, 1.0),
        (10.0, 9.0, 1.0),
    )
    DESIGNS: ClassVar[Dict[Country, FlagDesign]] = {
        Country.UNITED_STATES: FlagDesign(
            bands=["#b22234", "#ffffff"] * 6 + ["#b22234"], canton="#3c3b6e", canton_bands=7
        ),
        Country.FRANCE: FlagDesign(bands=["#002395", "#ffffff", "#ed2939"], vertical=True),
        Country.BELGIUM: FlagDesign(bands=["#000000", "#fae042", "#ed2939"], vertical=True),
        Country.GERMANY: FlagDesign(bands=["#000000", "#dd0000", "#ffce00"]),
        Country.ITALY: FlagDesign(bands=["#009246", "#ffffff", "#ce2b37"], vertical=True),
        Country.LUXEMBOURG: FlagDesign(bands=["#ed2939", "#ffffff", "#00a1de"]),
        Country.SPAIN: FlagDesign(bands=["#aa151b", "#f1bf00", "#aa151b"], weights=[1, 2, 1]),
        Country.SWITZERLAND: FlagDesign(bands=["#da291c"], cross="#ffffff", cross_width=0.19, cross_length=0.62),
        Country.UNITED_KINGDOM: FlagDesign(
            bands=["#012169"],
            saltire="#ffffff",
            saltire_inner="#c8102e",
            cross="#ffffff",
            cross_width=0.34,
            cross_inner="#c8102e",
            cross_inner_width=0.2,
        ),
        Country.CHINA: FlagDesign(bands=["#ee1c25"], stars="#ffff00"),
    }

    def __init__(self, logger: Optional[Logger] = None) -> None:
        """Initialize the painter, without any flag drawn yet.

        Args:
            logger (Optional[Logger]): The painter logger.
        """
        self.pixmaps: Dict[Tuple[Country, int], QPixmap] = {}
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _paint_bands(self, painter: QPainter, design: FlagDesign, area: QRectF) -> None:
        """Paint the bands of a flag, filling the whole flag.

        Args:
            painter (QPainter): The painter.
            design (FlagDesign): The flag design.
            area (QRectF): The flag area.
        """
        weights = design.weights if len(design.weights) == len(design.bands) else [1] * len(design.bands)
        total, start = sum(weights), 0.0
        for color, weight in zip(design.bands, weights, strict=True):
            if design.vertical:
                size = area.width() * weight / total
                band = QRectF(area.left() + start, area.top(), size, area.height())
            else:
                size = area.height() * weight / total
                band = QRectF(area.left(), area.top() + start, area.width(), size)
            painter.fillRect(band, QColor(color))
            start += size

    def _paint_canton(self, painter: QPainter, design: FlagDesign, area: QRectF) -> None:
        """Paint the upper hoist rectangle of a flag, over the bands it covers.

        Args:
            painter (QPainter): The painter.
            design (FlagDesign): The flag design.
            area (QRectF): The flag area.
        """
        if design.canton is None:
            return
        height = area.height() * design.canton_bands / len(design.bands)
        painter.fillRect(QRectF(area.left(), area.top(), area.width() * 0.4, height), QColor(design.canton))

    def _paint_saltire(self, painter: QPainter, design: FlagDesign, area: QRectF) -> None:
        """Paint the diagonal crosses of a flag, the wide one then the thin one.

        Args:
            painter (QPainter): The painter.
            design (FlagDesign): The flag design.
            area (QRectF): The flag area.
        """
        painter.save()
        painter.setClipRect(area)
        for color, width in ((design.saltire, 0.2), (design.saltire_inner, 0.067)):
            if color is None:
                continue
            pen = QPen(QColor(color), area.height() * width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawLine(area.topLeft(), area.bottomRight())
            painter.drawLine(area.bottomLeft(), area.topRight())
        painter.restore()

    def _paint_cross(self, painter: QPainter, design: FlagDesign, area: QRectF) -> None:
        """Paint the centred crosses of a flag, the wide one then the thin one.

        Args:
            painter (QPainter): The painter.
            design (FlagDesign): The flag design.
            area (QRectF): The flag area.
        """
        center = area.center()
        for color, width in ((design.cross, design.cross_width), (design.cross_inner, design.cross_inner_width)):
            if color is None:
                continue
            thickness = area.height() * width
            across = area.width() if design.cross_length is None else area.height() * design.cross_length
            along = area.height() if design.cross_length is None else area.height() * design.cross_length
            horizontal = QRectF(center.x() - across / 2, center.y() - thickness / 2, across, thickness)
            vertical = QRectF(center.x() - thickness / 2, center.y() - along / 2, thickness, along)
            painter.fillRect(horizontal, QColor(color))
            painter.fillRect(vertical, QColor(color))

    def _star(self, center: QPointF, radius: float) -> QPolygonF:
        """Build a five-pointed star, pointing up.

        Args:
            center (QPointF): The star centre.
            radius (float): The radius of its points.

        Returns:
            QPolygonF: The star outline.
        """
        points = []
        for index in range(10):
            angle = math.radians(-90 + index * 36)
            length = radius if index % 2 == 0 else radius * 0.382
            points.append(QPointF(center.x() + length * math.cos(angle), center.y() + length * math.sin(angle)))
        return QPolygonF(points)

    def _paint_stars(self, painter: QPainter, design: FlagDesign, area: QRectF) -> None:
        """Paint the stars of the upper hoist of a flag.

        Args:
            painter (QPainter): The painter.
            design (FlagDesign): The flag design.
            area (QRectF): The flag area.
        """
        if design.stars is None:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(design.stars))
        for x, y, radius in self.STARS:
            center = QPointF(area.left() + area.width() * x / 30, area.top() + area.height() * y / 20)
            painter.drawPolygon(self._star(center, area.height() * radius / 20))

    def _draw(self, country: Country, height: int) -> QPixmap:
        """Draw a flag, with a thin border.

        Args:
            country (Country): The flag country.
            height (int): The flag height, in pixels.

        Returns:
            QPixmap: The flag.
        """
        design = self.DESIGNS[country]
        pixmap = QPixmap(round(height * self.RATIO), height)
        pixmap.fill(Qt.GlobalColor.transparent)
        area = QRectF(pixmap.rect())
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_bands(painter, design, area)
        self._paint_canton(painter, design, area)
        self._paint_saltire(painter, design, area)
        self._paint_cross(painter, design, area)
        self._paint_stars(painter, design, area)
        painter.setPen(QPen(self.BORDER, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(area.adjusted(0.5, 0.5, -0.5, -0.5))
        painter.end()
        self.logger.debug("Flag of %s drawn (%d pixels high).", country.value, height)
        return pixmap

    ############################
    # Publicly Exposed Methods #
    ############################

    def pixmap(self, country: Country, height: int = 12) -> QPixmap:
        """Get the flag of a country, drawn once per height.

        Args:
            country (Country): The flag country.
            height (int): The flag height, in pixels. Its width is 1.5 times larger.

        Returns:
            QPixmap: The flag.
        """
        key = (country, height)
        if key not in self.pixmaps:
            self.pixmaps[key] = self._draw(country, height)
        return self.pixmaps[key]

    def icon(self, country: Country, height: int = 12) -> QIcon:
        """Get the flag icon of a country.

        Args:
            country (Country): The flag country.
            height (int): The flag height, in pixels.

        Returns:
            QIcon: The flag icon.
        """
        return QIcon(self.pixmap(country, height))
