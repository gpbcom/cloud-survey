from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QSpinBox, QToolButton, QWidget

# First Party Imports.
from gui.widgets.compact_combo import CompactCombo
from models.drivers.enums import DriverRole, DriverScope, MetricFamily, ProviderMetric
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.query.driver_query import DriverQuery

type DriverSelection = Tuple[Optional[ProviderMetric], List[ProviderMetric], List[ProviderMetric], DriverScope, int]


class DriverControls(QWidget):
    """The pickers of the "Rise drivers" analysis: target, criteria, controls, scope and lag.

    Attributes:
        DEFAULT_CRITERIA (ClassVar[Tuple[ProviderMetric, ...]]): The criteria checked at first (those the crawled
            data measure for most providers).
        MAX_CRITERIA (ClassVar[int]): The most criteria an analysis takes.
        MAX_CONTROLS (ClassVar[int]): The most controls an analysis takes.
        run_requested (pyqtSignal): Emitted when the analysis is asked for.
        export_requested (pyqtSignal): Emitted when the observations are asked for as CSV.
        changed (pyqtSignal): Emitted when a picker changes (the role legend follows).
        catalog (MetricCatalog): The definitions of the criteria and the targets.
        target_box (CompactCombo): The target.
        criteria_button (QToolButton): Opens the criteria, one checkable entry each, by family.
        controls_button (QToolButton): Opens the controls held constant in the partial correlations.
        scope_box (CompactCombo): The latest quarter of each provider, or every quarter (panel).
        lag_box (QSpinBox): How many quarters the criteria lead the target (panel only).
        run_button (QPushButton): Runs the analysis.
        export_button (QPushButton): Exports the observations as CSV.
        logger (Logger): The controls logger.
    """

    DEFAULT_CRITERIA: ClassVar[Tuple[ProviderMetric, ...]] = (
        ProviderMetric.PRODUCTS,
        ProviderMetric.CATEGORIES,
        ProviderMetric.AI_SHARE,
        ProviderMetric.DEVELOPER_SHARE,
        ProviderMetric.MARKETPLACE_SIZE,
        ProviderMetric.MENTIONS,
    )
    MAX_CRITERIA: ClassVar[int] = 16
    MAX_CONTROLS: ClassVar[int] = 4

    run_requested = pyqtSignal()
    export_requested = pyqtSignal()
    changed = pyqtSignal()

    def __init__(self, catalog: MetricCatalog, logger: Optional[Logger] = None) -> None:
        """Build the pickers.

        Args:
            catalog (MetricCatalog): The definitions of the criteria and the targets.
            logger (Optional[Logger]): The controls logger.
        """
        super().__init__()
        self.catalog = catalog
        self.logger = logger if logger else getLogger(__name__)
        self.target_box = CompactCombo(22)
        self.target_box.setToolTip("The measure of the rise to explain")
        for definition in catalog.targets():
            self.target_box.addItem(definition.label, definition.metric.value)
        self.criteria_button = QToolButton()
        self.criteria_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.criteria_button.setToolTip("The candidate drivers (at most 16, about one per 10 providers is stable)")
        self.criteria_button.setMenu(QMenu(self.criteria_button))
        self.controls_button = QToolButton()
        self.controls_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.controls_button.setToolTip("Held constant in the partial correlations (e.g. the catalogue size)")
        self.controls_button.setMenu(QMenu(self.controls_button))
        self.scope_box = CompactCombo(18)
        self.scope_box.addItem("Latest quarter", DriverScope.CROSS_SECTION.value)
        self.scope_box.addItem("Every quarter (panel)", DriverScope.PANEL.value)
        self.scope_box.setToolTip(
            "Latest quarter: one observation per provider. Panel: the yearly changes of every quarter, with "
            "provider and quarter effects (needs a history of crawls)."
        )
        self.lag_box = QSpinBox()
        self.lag_box.setRange(0, 8)
        self.lag_box.setValue(1)
        self.lag_box.setSuffix(" q lag")
        self.lag_box.setToolTip("How many quarters the criteria lead the target (panel only)")
        self.run_button = QPushButton("Run")
        self.run_button.setToolTip("Refresh the provider metrics if needed and run the analysis")
        self.export_button = QPushButton("Export CSV")
        self.export_button.setToolTip("Save the observations of the last analysis")
        self.export_button.setEnabled(False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for label, widget in (
            ("Target", self.target_box),
            ("", self.criteria_button),
            ("", self.controls_button),
            ("", self.scope_box),
            ("", self.lag_box),
        ):
            if label:
                layout.addWidget(QLabel(label))
            layout.addWidget(widget)
        layout.addStretch(1)
        layout.addWidget(self.run_button)
        layout.addWidget(self.export_button)
        self._fill(self.criteria_button, self.DEFAULT_CRITERIA)
        self._fill(self.controls_button, ())
        self._on_target()
        self._on_scope()
        self.target_box.currentIndexChanged.connect(self._on_target)
        self.scope_box.currentIndexChanged.connect(self._on_scope)
        self.lag_box.valueChanged.connect(self.changed)
        self.run_button.clicked.connect(self.run_requested)
        self.export_button.clicked.connect(self.export_requested)
        criteria_menu, controls_menu = self.criteria_button.menu(), self.controls_button.menu()
        if criteria_menu is not None:
            criteria_menu.triggered.connect(self._on_criterion)
        if controls_menu is not None:
            controls_menu.triggered.connect(self._on_control)
        self.logger.debug("Driver controls built with %d targets.", self.target_box.count())

    ############################
    # Internal Helpers Methods #
    ############################

    def _fill(self, button: QToolButton, checked: Tuple[ProviderMetric, ...]) -> None:
        """List every criterion in the menu of a button, by family.

        Args:
            button (QToolButton): The criteria or the controls button.
            checked (Tuple[ProviderMetric, ...]): The criteria checked at first.
        """
        menu = button.menu()
        if menu is None:
            return
        for family in MetricFamily:
            definitions = self.catalog.of_family(family)
            if not definitions:
                continue
            menu.addSection(family.value.replace("-", " ").capitalize())
            for definition in definitions:
                action = menu.addAction(definition.label)
                if action is None:
                    continue
                action.setCheckable(True)
                action.setChecked(definition.metric in checked)
                action.setData(definition.metric.value)
                action.setToolTip(definition.description)

    def _actions(self, button: QToolButton) -> List[QAction]:
        """Get the criteria entries of a button.

        Args:
            button (QToolButton): The criteria or the controls button.

        Returns:
            List[QAction]: Its checkable entries.
        """
        menu = button.menu()
        return [action for action in menu.actions() if action.isCheckable()] if menu is not None else []

    def _checked(self, button: QToolButton) -> List[ProviderMetric]:
        """Get the criteria checked in the menu of a button.

        Args:
            button (QToolButton): The criteria or the controls button.

        Returns:
            List[ProviderMetric]: The checked criteria, in the menu order.
        """
        return [
            ProviderMetric(str(action.data()))
            for action in self._actions(button)
            if action.isChecked() and action.isEnabled()
        ]

    def _target(self) -> Optional[ProviderMetric]:
        """Get the target picked.

        Returns:
            Optional[ProviderMetric]: The target, `None` without any.
        """
        data = self.target_box.currentData()
        return ProviderMetric(str(data)) if data else None

    def _label(self) -> None:
        """Write the number of checked criteria and controls on their buttons, and allow a run with criteria."""
        criteria, controls = self._checked(self.criteria_button), self._checked(self.controls_button)
        self.criteria_button.setText(f"Criteria ({len(criteria)}) ▾")
        self.controls_button.setText(f"Controls ({len(controls)}) ▾")
        self.run_button.setEnabled(bool(criteria) and self._target() is not None)
        self.changed.emit()

    def _on_target(self) -> None:
        """Disable the target among the criteria and the controls (a criterion cannot explain itself)."""
        target = self._target()
        for button in (self.criteria_button, self.controls_button):
            for action in self._actions(button):
                action.setEnabled(str(action.data()) != (target.value if target else ""))
        self._label()

    def _on_scope(self) -> None:
        """Allow the lag in a panel only."""
        self.lag_box.setEnabled(self.scope_box.currentData() == DriverScope.PANEL.value)
        self.changed.emit()

    def _limit(self, button: QToolButton, action: QAction, limit: int) -> None:
        """Uncheck an entry past the most a menu takes.

        Args:
            button (QToolButton): The criteria or the controls button.
            action (QAction): The entry just toggled.
            limit (int): The most checked entries.
        """
        if action.isChecked() and len(self._checked(button)) > limit:
            action.setChecked(False)
            self.logger.warning("At most %d entries can be checked.", limit)
        self._label()

    def _on_criterion(self, action: QAction) -> None:
        """Count the criteria once one is toggled.

        Args:
            action (QAction): The toggled criterion.
        """
        self._limit(self.criteria_button, action, self.MAX_CRITERIA)

    def _on_control(self, action: QAction) -> None:
        """Count the controls once one is toggled.

        Args:
            action (QAction): The toggled control.
        """
        self._limit(self.controls_button, action, self.MAX_CONTROLS)

    ############################
    # Publicly Exposed Methods #
    ############################

    def set_checked(self, criteria: List[ProviderMetric], controls: Optional[List[ProviderMetric]] = None) -> None:
        """Check criteria and controls, unchecking the others.

        Args:
            criteria (List[ProviderMetric]): The criteria.
            controls (Optional[List[ProviderMetric]]): The controls, none by default.
        """
        for button, wanted in ((self.criteria_button, criteria), (self.controls_button, controls or [])):
            values = {metric.value for metric in wanted}
            for action in self._actions(button):
                action.setChecked(str(action.data()) in values)
        self._label()

    def selection(self) -> DriverSelection:
        """Get what is picked, even when no analysis can run yet.

        Returns:
            DriverSelection: The target, the criteria, the controls, the scope and the lag.
        """
        target = self._target()
        criteria = [metric for metric in self._checked(self.criteria_button) if metric is not target]
        controls = [metric for metric in self._checked(self.controls_button) if metric is not target]
        scope = DriverScope(str(self.scope_box.currentData() or DriverScope.CROSS_SECTION.value))
        return target, criteria, controls, scope, self.lag_box.value()

    def open_picker(self, role: DriverRole) -> None:
        """Open the picker of a role (a chip of the role legend was clicked).

        Args:
            role (DriverRole): The role.
        """
        self.logger.debug("Opening the %s picker.", role.value)
        match role:
            case DriverRole.TARGET:
                self.target_box.setFocus()
                self.target_box.showPopup()
            case DriverRole.CRITERION:
                self.criteria_button.showMenu()
            case DriverRole.CONTROL:
                self.controls_button.showMenu()
            case DriverRole.SCOPE:
                self.scope_box.setFocus()
                self.scope_box.showPopup()
            case DriverRole.LAG:
                if not self.lag_box.isEnabled():
                    self.scope_box.setCurrentIndex(self.scope_box.findData(DriverScope.PANEL.value))
                self.lag_box.setFocus()
                self.lag_box.selectAll()

    def query(self) -> Optional[DriverQuery]:
        """Build the analysis picked.

        Returns:
            Optional[DriverQuery]: The analysis, `None` without a target or a criterion.
        """
        target = self._target()
        criteria = [metric for metric in self._checked(self.criteria_button) if metric is not target]
        if target is None or not criteria:
            return None
        scope = DriverScope(str(self.scope_box.currentData()))
        return DriverQuery(
            target=target,
            criteria=criteria[: self.MAX_CRITERIA],
            controls=[metric for metric in self._checked(self.controls_button) if metric is not target][
                : self.MAX_CONTROLS
            ],
            scope=scope,
            lag=self.lag_box.value() if scope is DriverScope.PANEL else 0,
        )
