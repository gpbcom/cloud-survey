from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QMenu, QToolButton, QWidget

# First Party Imports.
from gui.analysis.markets.notes.markets_tooltips import MarketsTooltips
from gui.widgets.compact_combo import CompactCombo
from models.history.chronology import Chronology
from models.markets.enums import MarketControl, PriceScale, StockView
from models.markets.markets_catalog import MarketsCatalog


class StockControls(QWidget):
    """The pickers of the stock chart: what it shows, the companies, the currency, the scale and the listings.

    Attributes:
        DEFAULT_COMPANIES (ClassVar[Tuple[str, ...]]): The companies picked at first.
        CURRENCIES (ClassVar[Tuple[Tuple[str, str], ...]]): The currency choices: their name and value.
        SCALES (ClassVar[Tuple[Tuple[str, PriceScale], ...]]): The scale choices.
        VIEWS (ClassVar[Tuple[Tuple[str, StockView], ...]]): The view choices.
        changed (pyqtSignal): Emitted when a picker changes.
        catalog (MarketsCatalog): The listings and the regions.
        view_box (CompactCombo): Listings, region indexes or valuation points.
        companies_button (QToolButton): The companies drawn, by region of headquarters (a checkable menu).
        currency_box (CompactCombo): Each listing in its own currency, or converted.
        scale_box (CompactCombo): Linear, logarithmic or indexed to 100.
        secondary_box (QCheckBox): Whether the secondary listings (ADRs, second exchanges) are drawn too.
        derivative_box (QCheckBox): Whether the chart draws the rate of change of each line.
        picked (Set[str]): The companies checked.
        logger (Logger): The controls logger.
    """

    DEFAULT_COMPANIES: ClassVar[Tuple[str, ...]] = ("ibm", "microsoft", "apple", "google", "amazon", "nvidia", "tsmc")
    CURRENCIES: ClassVar[Tuple[Tuple[str, str], ...]] = (
        ("Listing currency", "listing"),
        ("US dollar", "USD"),
        ("Euro", "EUR"),
        ("Pound sterling", "GBP"),
    )
    SCALES: ClassVar[Tuple[Tuple[str, PriceScale], ...]] = (
        ("Indexed (100 at start)", PriceScale.INDEXED),
        ("Logarithmic", PriceScale.LOG),
        ("Linear", PriceScale.LINEAR),
    )
    VIEWS: ClassVar[Tuple[Tuple[str, StockView], ...]] = (
        ("Listings", StockView.LISTINGS),
        ("Region indexes", StockView.REGIONS),
        ("Valuation points", StockView.VALUATIONS),
    )

    changed = pyqtSignal()

    def __init__(
        self, catalog: MarketsCatalog, chronology: Optional[Chronology], logger: Optional[Logger] = None
    ) -> None:
        """Build the pickers.

        Args:
            catalog (MarketsCatalog): The listings and the regions.
            chronology (Optional[Chronology]): Names the companies and gives their country.
            logger (Optional[Logger]): The controls logger.
        """
        super().__init__()
        self.catalog = catalog
        self.logger = logger if logger else getLogger(__name__)
        self.picked: Set[str] = set(self.DEFAULT_COMPANIES)
        self.view_box = CompactCombo(16)
        self.view_box.setToolTip(
            "Listings: a line per listing of the companies picked. Region indexes: an equal-weight index of the "
            "primary listings per region of headquarters. Valuation points: the sourced IPOs, deals, private rounds "
            "and market caps (USD bn), for the companies without a price history too."
        )
        for name, view in self.VIEWS:
            self.view_box.addItem(name, view.value)
        self.companies_button = QToolButton()
        self.companies_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.companies_button.setToolTip("The companies drawn, by region of headquarters")
        self.companies_button.setMenu(QMenu(self.companies_button))
        self.currency_box = CompactCombo(14)
        self.currency_box.setToolTip("Each listing in its own currency, or converted on each day (FRED rates)")
        for name, currency in self.CURRENCIES:
            self.currency_box.addItem(name, currency)
        self.scale_box = CompactCombo(16)
        self.scale_box.setToolTip("Indexed: each line rebased to 100 at its first point in the window")
        for name, scale in self.SCALES:
            self.scale_box.addItem(name, scale.value)
        self.secondary_box = QCheckBox("Secondary listings")
        self.secondary_box.setToolTip("Draw the ADRs and the second exchanges too (dashed)")
        self.derivative_box = QCheckBox("Rate of change")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Show"))
        for widget in (
            self.view_box,
            self.companies_button,
            self.currency_box,
            self.scale_box,
            self.secondary_box,
            self.derivative_box,
        ):
            layout.addWidget(widget)
        layout.addStretch(1)
        self._fill(chronology)
        self.view_box.currentIndexChanged.connect(self.changed)
        self.currency_box.currentIndexChanged.connect(self.changed)
        self.scale_box.currentIndexChanged.connect(self.changed)
        self.secondary_box.toggled.connect(self.changed)
        menu = self.companies_button.menu()
        if menu is not None:
            menu.triggered.connect(self._on_company)
        self.logger.debug("Stock controls built with %d companies.", len(self.picked))

    ############################
    # Internal Helpers Methods #
    ############################

    def _caption(self) -> None:
        """Print the number of companies picked on the button."""
        self.companies_button.setText(f"Companies ({len(self.picked)})")

    def _fill(self, chronology: Optional[Chronology]) -> None:
        """List the companies with a listing in the menu, by region of headquarters.

        Args:
            chronology (Optional[Chronology]): Names the companies and gives their country.
        """
        menu = self.companies_button.menu()
        if menu is None:
            return
        listed = sorted({listing.company for listing in self.catalog.listings})
        by_region: Dict[str, List[Tuple[str, str]]] = {}
        for key in listed:
            company = chronology.company(key) if chronology else None
            region = self.catalog.region_of(company.country if company else None)
            by_region.setdefault(region.label if region else "Other", []).append(
                (company.label if company else key, key)
            )
        for region_label in sorted(by_region):
            menu.addSection(region_label)
            for label, key in sorted(by_region[region_label]):
                action = QAction(label, menu)
                action.setCheckable(True)
                action.setChecked(key in self.picked)
                action.setData(key)
                menu.addAction(action)
        self._caption()

    def _on_company(self, action: QAction) -> None:
        """Pick or drop a company.

        Args:
            action (QAction): Its menu entry.
        """
        key = str(action.data())
        if action.isChecked():
            self.picked.add(key)
        else:
            self.picked.discard(key)
        self._caption()
        self.changed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def explain(self, tooltips: MarketsTooltips) -> None:
        """Write the tooltip of every picker and of every choice of its list.

        Args:
            tooltips (MarketsTooltips): The tooltip writer.
        """
        for box, control in (
            (self.view_box, MarketControl.VIEW),
            (self.currency_box, MarketControl.CURRENCY),
            (self.scale_box, MarketControl.SCALE),
        ):
            box.setToolTip(tooltips.control(control))
            for index in range(box.count()):
                value, label = str(box.itemData(index)), box.itemText(index)
                box.setItemData(index, tooltips.option(control, value, label), Qt.ItemDataRole.ToolTipRole)
        self.companies_button.setToolTip(tooltips.control(MarketControl.COMPANIES))
        self.secondary_box.setToolTip(tooltips.control(MarketControl.SECONDARY))
        self.derivative_box.setToolTip(tooltips.control(MarketControl.DERIVATIVE))
        self.logger.debug("Stock controls explained.")

    def view(self) -> StockView:
        """Get what the chart shows.

        Returns:
            StockView: Listings, region indexes or valuation points.
        """
        return StockView(str(self.view_box.currentData()))

    def companies(self) -> List[str]:
        """Get the companies picked.

        Returns:
            List[str]: Their keys, sorted.
        """
        return sorted(self.picked)

    def currency(self) -> str:
        """Get the currency picked.

        Returns:
            str: `listing`, or a currency code.
        """
        return str(self.currency_box.currentData())

    def scale(self) -> PriceScale:
        """Get the scale picked.

        Returns:
            PriceScale: Linear, logarithmic or indexed.
        """
        return PriceScale(str(self.scale_box.currentData()))

    def secondary(self) -> bool:
        """Tell whether the secondary listings are drawn.

        Returns:
            bool: Whether they are.
        """
        return self.secondary_box.isChecked()

    def set_companies(self, keys: Sequence[str]) -> None:
        """Pick companies, as a click on a leader band does (the listings view is shown).

        Args:
            keys (Sequence[str]): Their keys (those without a listing are ignored).
        """
        listed = {listing.company for listing in self.catalog.listings}
        self.picked = {key for key in keys if key in listed} or self.picked
        menu = self.companies_button.menu()
        for action in menu.actions() if menu else []:
            if action.isCheckable():
                action.setChecked(str(action.data()) in self.picked)
        self._caption()
        self.view_box.blockSignals(True)
        self.view_box.setCurrentIndex(self.view_box.findData(StockView.LISTINGS.value))
        self.view_box.blockSignals(False)
        self.changed.emit()
