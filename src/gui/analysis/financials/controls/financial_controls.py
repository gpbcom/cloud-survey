from __future__ import annotations

# Standard Library Imports.
import html
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence, Set, Tuple

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QMenu, QToolButton, QWidget

# First Party Imports.
from gui.widgets.compact_combo import CompactCombo
from models.companies.enums import CompanyIndicator, FinancialControl, FinancialGranularity
from models.companies.help.financials_help import FinancialsHelp
from models.companies.help.indicator_help import IndicatorHelp

type CompanyChoice = Tuple[str, str, str]


class FinancialControls(QWidget):
    """The pickers of the company financials card: the companies, the indicator, the period, the currency.

    Attributes:
        DEFAULT_COMPANIES (ClassVar[Tuple[str, ...]]): The companies picked at first.
        DEFAULT_INDICATOR (ClassVar[CompanyIndicator]): The indicator picked at first.
        PERIODS (ClassVar[Tuple[Tuple[str, FinancialGranularity], ...]]): The period choices.
        CURRENCIES (ClassVar[Tuple[Tuple[str, str], ...]]): The currency choices: their name and value.
        OWN (ClassVar[str]): The value of the company's own currency.
        changed (pyqtSignal): Emitted when a picker changes.
        helps (FinancialsHelp): The titles, families and explanations of the indicators.
        companies_button (QToolButton): The companies drawn, by region of headquarters (a checkable menu).
        indicator_button (QToolButton): The indicator drawn, by family (an exclusive menu).
        period_box (CompactCombo): Fiscal years, quarters or trailing twelve months.
        currency_box (CompactCombo): The company's own currency or US dollars.
        derivative_box (QCheckBox): Whether the chart draws the rate of change of each line.
        picked (Set[str]): The companies checked.
        current (CompanyIndicator): The indicator picked.
        logger (Logger): The controls logger.
    """

    DEFAULT_COMPANIES: ClassVar[Tuple[str, ...]] = ("ibm", "microsoft", "google", "amazon", "oracle", "alibaba")
    DEFAULT_INDICATOR: ClassVar[CompanyIndicator] = CompanyIndicator.NET_INCOME
    PERIODS: ClassVar[Tuple[Tuple[str, FinancialGranularity], ...]] = (
        ("Fiscal years", FinancialGranularity.YEAR),
        ("Quarters", FinancialGranularity.QUARTER),
        ("Trailing 12 months", FinancialGranularity.TTM),
    )
    CURRENCIES: ClassVar[Tuple[Tuple[str, str], ...]] = (("Own currency", "own"), ("US dollar", "USD"))
    OWN: ClassVar[str] = "own"

    changed = pyqtSignal()

    def __init__(
        self, helps: FinancialsHelp, companies: Sequence[CompanyChoice], logger: Optional[Logger] = None
    ) -> None:
        """Build the pickers.

        Args:
            helps (FinancialsHelp): The titles, families and explanations of the indicators.
            companies (Sequence[CompanyChoice]): The key, name and region of every company offered.
            logger (Optional[Logger]): The controls logger.
        """
        super().__init__()
        self.helps = helps
        self.logger = logger if logger else getLogger(__name__)
        offered = {key for key, _, _ in companies}
        self.picked: Set[str] = {key for key in self.DEFAULT_COMPANIES if key in offered}
        self.current = self.DEFAULT_INDICATOR
        self.companies_button = QToolButton()
        self.companies_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.companies_button.setMenu(QMenu(self.companies_button))
        self.indicator_button = QToolButton()
        self.indicator_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.indicator_button.setMenu(QMenu(self.indicator_button))
        self.period_box = CompactCombo(16)
        for name, granularity in self.PERIODS:
            self.period_box.addItem(name, granularity.value)
        self.currency_box = CompactCombo(12)
        for name, currency in self.CURRENCIES:
            self.currency_box.addItem(name, currency)
        self.derivative_box = QCheckBox("Rate of change")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel("Show"))
        for widget in (
            self.indicator_button,
            self.companies_button,
            self.period_box,
            self.currency_box,
            self.derivative_box,
        ):
            layout.addWidget(widget)
        layout.addStretch(1)
        self._fill_companies(companies)
        self._fill_indicators()
        self._explain()
        self.period_box.currentIndexChanged.connect(self.changed)
        self.currency_box.currentIndexChanged.connect(self.changed)
        self.logger.debug("Financial controls built: %d companies offered, %d picked.", len(offered), len(self.picked))

    ############################
    # Internal Helpers Methods #
    ############################

    def _tooltip(self, control: FinancialControl) -> str:
        """Write the tooltip of a control.

        Args:
            control (FinancialControl): The control.

        Returns:
            str: Its title and what it changes, empty when it has no help.
        """
        found = self.helps.control(control)
        return f"<qt><b>{html.escape(found.title)}</b><br>{html.escape(found.summary)}</qt>" if found else ""

    def _indicator_tooltip(self, item: IndicatorHelp) -> str:
        """Write the tooltip of an indicator.

        Args:
            item (IndicatorHelp): Its help.

        Returns:
            str: Its title, formula, meaning and caveat.
        """
        caveat = f"<br><i>{html.escape(item.caveat)}</i>" if item.caveat else ""
        return (
            f"<qt><b>{html.escape(item.title)}</b><br>{html.escape(item.formula)}<br>"
            f"{html.escape(item.summary)}{caveat}</qt>"
        )

    def _title(self, indicator: CompanyIndicator) -> str:
        """Name an indicator.

        Args:
            indicator (CompanyIndicator): The indicator.

        Returns:
            str: Its title, its key when it has no help.
        """
        found = self.helps.indicator(indicator)
        return found.title if found else indicator.value

    def _captions(self) -> None:
        """Print the indicator and the number of companies picked on their buttons."""
        self.indicator_button.setText(self._title(self.current))
        self.companies_button.setText(f"Companies ({len(self.picked)})")

    def _fill_companies(self, companies: Sequence[CompanyChoice]) -> None:
        """List the companies in their menu, by region of headquarters.

        Args:
            companies (Sequence[CompanyChoice]): The key, name and region of every company offered.
        """
        menu = self.companies_button.menu()
        if menu is None:
            return
        by_region: Dict[str, List[Tuple[str, str]]] = {}
        for key, label, region in companies:
            by_region.setdefault(region, []).append((label, key))
        for region in sorted(by_region):
            menu.addSection(region)
            for label, key in sorted(by_region[region]):
                action = QAction(label, menu)
                action.setCheckable(True)
                action.setChecked(key in self.picked)
                action.setData(key)
                menu.addAction(action)
        menu.triggered.connect(self._on_company)

    def _fill_indicators(self) -> None:
        """List the indicators in their menu, by family, one picked at a time."""
        menu = self.indicator_button.menu()
        if menu is None:
            return
        menu.setToolTipsVisible(True)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for family in self.helps.families:
            menu.addSection(family.title)
            for item in self.helps.family_of(family.family):
                action = QAction(item.title, menu)
                action.setCheckable(True)
                action.setChecked(item.indicator is self.current)
                action.setData(item.indicator.value)
                action.setToolTip(self._indicator_tooltip(item))
                group.addAction(action)
                menu.addAction(action)
        menu.triggered.connect(self._on_indicator)

    def _explain(self) -> None:
        """Write the tooltip of every picker."""
        for widget, control in (
            (self.companies_button, FinancialControl.COMPANIES),
            (self.indicator_button, FinancialControl.INDICATOR),
            (self.period_box, FinancialControl.PERIOD),
            (self.currency_box, FinancialControl.CURRENCY),
            (self.derivative_box, FinancialControl.DERIVATIVE),
        ):
            widget.setToolTip(self._tooltip(control))
        self._captions()

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
        self._captions()
        self.changed.emit()

    def _on_indicator(self, action: QAction) -> None:
        """Pick an indicator.

        Args:
            action (QAction): Its menu entry.
        """
        self.current = CompanyIndicator(str(action.data()))
        self._captions()
        self.logger.debug("Indicator %s picked.", self.current.value)
        self.changed.emit()

    ############################
    # Publicly Exposed Methods #
    ############################

    def companies(self) -> List[str]:
        """Get the companies picked.

        Returns:
            List[str]: Their keys, sorted.
        """
        return sorted(self.picked)

    def indicator(self) -> CompanyIndicator:
        """Get the indicator picked.

        Returns:
            CompanyIndicator: The indicator.
        """
        return self.current

    def period(self) -> FinancialGranularity:
        """Get the period picked.

        Returns:
            FinancialGranularity: A fiscal year, a quarter or the trailing twelve months.
        """
        return FinancialGranularity(str(self.period_box.currentData()))

    def in_usd(self) -> bool:
        """Tell whether the amounts are drawn in US dollars.

        Returns:
            bool: Whether they are (else in each company's own currency).
        """
        return str(self.currency_box.currentData()) != self.OWN

    def set_indicator(self, indicator: CompanyIndicator) -> None:
        """Pick an indicator from the code, as its menu entry does.

        Args:
            indicator (CompanyIndicator): The indicator.
        """
        menu = self.indicator_button.menu()
        for action in menu.actions() if menu else []:
            if action.isCheckable() and str(action.data()) == indicator.value:
                action.setChecked(True)
        self.current = indicator
        self._captions()
        self.changed.emit()

    def set_companies(self, keys: Sequence[str]) -> None:
        """Pick companies from the code (those not offered are ignored).

        Args:
            keys (Sequence[str]): Their keys.
        """
        menu = self.companies_button.menu()
        actions = [action for action in (menu.actions() if menu else []) if action.isCheckable()]
        offered = {str(action.data()) for action in actions}
        self.picked = {key for key in keys if key in offered} or self.picked
        for action in actions:
            action.setChecked(str(action.data()) in self.picked)
        self._captions()
        self.changed.emit()
