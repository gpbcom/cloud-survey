from __future__ import annotations

# Standard Library Imports.
import html
from functools import partial
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QWidget

# First Party Imports.
from gui.analysis.drivers.notes.help_chip import HelpChip
from gui.layout.flow_layout import FlowLayout
from gui.theme import Theme
from models.drivers.enums import DriverRole, DriverScope, ProviderMetric
from models.drivers.help.driver_help import DriverHelp
from models.drivers.metrics.metric_catalog import MetricCatalog

type RoleValues = Dict[DriverRole, List[str]]


class RoleLegend(QWidget):
    """The legend of the roles of the parameters: a chip per role, its current value and what it does.

    Attributes:
        SHOWN_NAMES (ClassVar[int]): The names written on a chip, the others counted (`+2`).
        SCOPE_NAMES (ClassVar[Dict[DriverScope, str]]): The name of each scope.
        role_clicked (pyqtSignal): Emitted with the role (its value) of a clicked chip: its picker opens.
        theme (Theme): The application theme.
        help (DriverHelp): The explanation of each role.
        chips (Dict[DriverRole, HelpChip]): The chip of each role, in the order of the explanations.
        logger (Logger): The legend logger.

    Notes:
        Each chip is coloured like its role everywhere else (the scatter axes, the importance bars). Hovering a chip
        explains the role and how the statistics use it, clicking it opens its picker.
    """

    SHOWN_NAMES: ClassVar[int] = 2
    SCOPE_NAMES: ClassVar[Dict[DriverScope, str]] = {
        DriverScope.CROSS_SECTION: "latest quarter",
        DriverScope.PANEL: "every quarter (panel)",
    }

    role_clicked = pyqtSignal(str)

    def __init__(self, theme: Theme, help_: DriverHelp, logger: Optional[Logger] = None) -> None:
        """Build the legend, a chip per role.

        Args:
            theme (Theme): The application theme.
            help_ (DriverHelp): The explanation of each role.
            logger (Optional[Logger]): The legend logger.
        """
        super().__init__()
        self.theme, self.help = theme, help_
        self.logger = logger if logger else getLogger(__name__)
        layout = FlowLayout(self, gap=6, logger=self.logger)
        layout.setContentsMargins(0, 0, 0, 0)
        caption = QLabel("Roles")
        caption.setObjectName("muted")
        caption.setToolTip(
            "The role of each parameter in the analysis: hover a chip to learn it, click it to change it"
        )
        layout.addWidget(caption)
        self.chips: Dict[DriverRole, HelpChip] = {}
        ordered = [entry.role for entry in help_.roles] + [role for role in DriverRole if help_.role(role) is None]
        for role in ordered:
            explained = help_.role(role)
            chip = HelpChip(
                theme,
                theme.driver_role_color(role),
                explained.symbol if explained else "•",
                explained.title if explained else role.value.capitalize(),
                self.logger,
            )
            chip.clicked.connect(partial(self._on_chip, role))
            layout.addWidget(chip)
            self.chips[role] = chip
        self.logger.debug("Role legend built with %d roles.", len(self.chips))

    ############################
    # Internal Helpers Methods #
    ############################

    def _short(self, names: List[str], empty: str) -> str:
        """Write names on a chip: the first ones, the others counted.

        Args:
            names (List[str]): The names.
            empty (str): What to write without a name.

        Returns:
            str: E.g. `Products, Categories +3`.
        """
        if not names:
            return empty
        shown = ", ".join(names[: self.SHOWN_NAMES])
        hidden = len(names) - self.SHOWN_NAMES
        return f"{shown} +{hidden}" if hidden > 0 else shown

    def _tooltip(self, role: DriverRole, names: List[str], unused: bool) -> str:
        """Write the explanation of a role, in its colour, with its current value.

        Args:
            role (DriverRole): The role.
            names (List[str]): Its current value, a name each.
            unused (bool): Whether the role plays no part in the analysis picked.

        Returns:
            str: The rich text explanation.
        """
        explained = self.help.role(role)
        color = self.theme.DRIVER_ROLE_COLORS[role]
        title = html.escape(explained.title if explained else role.value)
        symbol = html.escape(explained.symbol if explained else "")
        parts = [f"<p style='margin:0'><b style='color:{color}'>{symbol} {title}</b>"]
        if explained:
            parts.append(f" — {html.escape(explained.summary)}</p><p>{html.escape(explained.details)}</p>")
        current = "<br>".join(f"• {html.escape(name)}" for name in names) if names else "<i>none</i>"
        parts.append(f"<p style='margin:0'><b>Now:</b><br>{current}</p>")
        if unused:
            parts.append("<p style='margin-top:6px'><i>Not used by the analysis picked.</i></p>")
        parts.append(f"<p style='margin-top:6px;color:{self.theme.TEXT_MUTED}'>Click to change it.</p>")
        return "<qt>" + "".join(parts) + "</qt>"

    def _on_chip(self, role: DriverRole) -> None:
        """Ask for the picker of a clicked chip.

        Args:
            role (DriverRole): The role of the chip.
        """
        self.logger.debug("Role chip %s clicked.", role.value)
        self.role_clicked.emit(role.value)

    ############################
    # Publicly Exposed Methods #
    ############################

    def show_selection(
        self,
        catalog: MetricCatalog,
        target: Optional[ProviderMetric],
        criteria: List[ProviderMetric],
        controls: List[ProviderMetric],
        scope: DriverScope,
        lag: int,
    ) -> None:
        """Show the current value of each role.

        Args:
            catalog (MetricCatalog): The names of the metrics.
            target (Optional[ProviderMetric]): The target picked, if any.
            criteria (List[ProviderMetric]): The criteria picked.
            controls (List[ProviderMetric]): The controls picked.
            scope (DriverScope): The scope picked.
            lag (int): The lag picked.
        """
        panel = scope is DriverScope.PANEL
        values: RoleValues = {
            DriverRole.TARGET: [catalog.label(target)] if target else [],
            DriverRole.CRITERION: [catalog.label(metric) for metric in criteria],
            DriverRole.CONTROL: [catalog.label(metric) for metric in controls],
            DriverRole.SCOPE: [self.SCOPE_NAMES[scope]],
            DriverRole.LAG: [f"{lag} quarter{'s' if lag != 1 else ''}"] if panel else [],
        }
        counts = {DriverRole.CRITERION: len(criteria), DriverRole.CONTROL: len(controls)}
        for role, chip in self.chips.items():
            names = values[role]
            unused = role is DriverRole.LAG and not panel
            text = self._short(names, "not used" if unused else "none")
            if role in counts and names:
                text = f"{counts[role]} · {text}"
            chip.set_content(text, self._tooltip(role, names, unused), dimmed=unused or not names)
