from __future__ import annotations

# Standard Library Imports.
import html
from functools import partial
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QLabel, QWidget

# First Party Imports.
from gui.analysis.drivers.notes.help_chip import HelpChip
from gui.layout.flow_layout import FlowLayout
from gui.theme import Theme
from models.drivers.enums import WarningSeverity
from models.drivers.help.driver_help import DriverHelp
from models.drivers.metrics.metric_catalog import MetricCatalog
from models.drivers.results.driver_warning import DriverWarning


class WarningBoard(QWidget):
    """The caveats of the last analysis: a chip per warning, coloured by severity, explained on hover.

    Attributes:
        ORDER (ClassVar[Dict[WarningSeverity, int]]): The rank of each severity, the most limiting first.
        SEVERITY_NAMES (ClassVar[Dict[WarningSeverity, str]]): What each severity means, in a few words.
        subjects_picked (pyqtSignal): Emitted with the criteria (their values) of a clicked warning, an empty list
            when it is clicked again.
        theme (Theme): The application theme.
        help (DriverHelp): The explanation of each warning.
        catalog (MetricCatalog): The names of the criteria.
        warnings (List[DriverWarning]): The warnings shown, in the order of their chips.
        chips (List[HelpChip]): The chips shown.
        selected (Optional[int]): The warning whose criteria are highlighted, if any.
        caption (QLabel): The caption of the board, with the number of caveats.
        logger (Logger): The board logger.

    Notes:
        Hovering a chip tells what the warning says for this run, what it means and what to do. Clicking it
        highlights the criteria it is about.
    """

    ORDER: ClassVar[Dict[WarningSeverity, int]] = {
        WarningSeverity.BLOCKING: 0,
        WarningSeverity.CAUTION: 1,
        WarningSeverity.INFO: 2,
    }
    SEVERITY_NAMES: ClassVar[Dict[WarningSeverity, str]] = {
        WarningSeverity.BLOCKING: "Blocking: a part of the analysis could not run",
        WarningSeverity.CAUTION: "Caution: read the results with care",
        WarningSeverity.INFO: "Information: something was left out, the rest stands",
    }

    subjects_picked = pyqtSignal(list)

    def __init__(
        self, theme: Theme, help_: DriverHelp, catalog: MetricCatalog, logger: Optional[Logger] = None
    ) -> None:
        """Build an empty board, hidden until an analysis is shown.

        Args:
            theme (Theme): The application theme.
            help_ (DriverHelp): The explanation of each warning.
            catalog (MetricCatalog): The names of the criteria.
            logger (Optional[Logger]): The board logger.
        """
        super().__init__()
        self.theme, self.help, self.catalog = theme, help_, catalog
        self.logger = logger if logger else getLogger(__name__)
        self.warnings: List[DriverWarning] = []
        self.chips: List[HelpChip] = []
        self.selected: Optional[int] = None
        self.flow = FlowLayout(self, gap=6, logger=self.logger)
        self.flow.setContentsMargins(0, 0, 0, 0)
        self.caption = QLabel("Caveats")
        self.caption.setObjectName("muted")
        self.caption.setToolTip("What limits the conclusions of the last analysis: hover a chip to learn more")
        self.flow.addWidget(self.caption)
        self.setVisible(False)

    ############################
    # Internal Helpers Methods #
    ############################

    def _clear(self) -> None:
        """Remove every chip."""
        self.logger.debug("Removing the %d chips of the warning board.", len(self.chips))
        for chip in self.chips:
            self.flow.removeWidget(chip)
            chip.deleteLater()
        self.chips, self.warnings, self.selected = [], [], None

    def _severity(self, warning: DriverWarning) -> WarningSeverity:
        """Get how much a warning limits the conclusions.

        Args:
            warning (DriverWarning): The warning.

        Returns:
            WarningSeverity: Its severity, a caution when it has no explanation.
        """
        explained = self.help.warning(warning.kind)
        return explained.severity if explained else WarningSeverity.CAUTION

    def _names(self, warning: DriverWarning) -> List[str]:
        """Name the criteria of a warning.

        Args:
            warning (DriverWarning): The warning.

        Returns:
            List[str]: Their labels.
        """
        return [self.catalog.label(metric) for metric in warning.subjects]

    def _tooltip(self, warning: DriverWarning) -> str:
        """Explain a warning: its severity, this run, what it means and what to do.

        Args:
            warning (DriverWarning): The warning.

        Returns:
            str: The rich text explanation.
        """
        severity = self._severity(warning)
        explained = self.help.warning(warning.kind)
        if explained is None:
            self.logger.warning("The warning %s is not explained in the drivers help.", warning.kind.value)
        color = self.theme.WARNING_COLORS[severity]
        title = html.escape(explained.title if explained else warning.kind.value)
        parts = [
            f"<p style='margin:0'><b style='color:{color}'>{self.theme.WARNING_SYMBOLS[severity]} {title}</b></p>",
            f"<p style='margin:0;color:{color}'>{html.escape(self.SEVERITY_NAMES[severity])}</p>",
            f"<p><b>This run:</b> {html.escape(warning.message)}</p>",
        ]
        names = self._names(warning)
        if names:
            parts.append("<p><b>Concerned:</b> " + ", ".join(html.escape(name) for name in names) + "</p>")
        if explained:
            parts.append(f"<p><b>What it means:</b> {html.escape(explained.meaning)}</p>")
            parts.append(f"<p><b>What to do:</b> {html.escape(explained.remedy)}</p>")
        if names:
            parts.append(f"<p style='color:{self.theme.TEXT_MUTED}'>Click to highlight them in the table.</p>")
        return "<qt>" + "".join(parts) + "</qt>"

    def _add(self, accent: QColor, symbol: str, title: str, value: str, tooltip: str) -> HelpChip:
        """Add a chip to the board.

        Args:
            accent (QColor): Its colour.
            symbol (str): Its glyph.
            title (str): Its title.
            value (str): Its value.
            tooltip (str): Its explanation.

        Returns:
            HelpChip: The chip.
        """
        chip = HelpChip(self.theme, accent, symbol, title, self.logger)
        chip.set_content(value, tooltip)
        self.flow.addWidget(chip)
        self.chips.append(chip)
        return chip

    def _on_chip(self, index: int) -> None:
        """Highlight the criteria of a clicked warning, or stop when it is clicked again.

        Args:
            index (int): The warning clicked.
        """
        self.selected = None if self.selected == index else index
        for position, chip in enumerate(self.chips):
            chip.set_selected(position == self.selected)
        subjects = [metric.value for metric in self.warnings[index].subjects] if self.selected is not None else []
        self.logger.debug("Warning %d picked: %d criteria highlighted.", index, len(subjects))
        self.subjects_picked.emit(subjects)

    ############################
    # Publicly Exposed Methods #
    ############################

    def show_warnings(self, warnings: List[DriverWarning]) -> None:
        """Show the warnings of an analysis, the most limiting first, or that nothing limits it.

        Args:
            warnings (List[DriverWarning]): The warnings.
        """
        self._clear()
        ordered = sorted(warnings, key=lambda warning: self.ORDER[self._severity(warning)])
        for index, warning in enumerate(ordered):
            severity = self._severity(warning)
            explained = self.help.warning(warning.kind)
            names = self._names(warning)
            value = ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")
            chip = self._add(
                self.theme.warning_color(severity),
                self.theme.WARNING_SYMBOLS[severity],
                explained.title if explained else warning.kind.value,
                value,
                self._tooltip(warning),
            )
            chip.clicked.connect(partial(self._on_chip, index))
            self.warnings.append(warning)
        if not warnings:
            self.logger.debug("No caveat limits the analysis.")
            self._add(
                QColor(self.theme.DRIVER_POSITIVE),
                "✓",
                "No caveat",
                "",
                "<qt><p style='margin:0'><b>No caveat</b></p><p>Nothing limits the conclusions beyond what the "
                "intervals and the leave-one-out R² show.</p></qt>",
            )
        self.caption.setText(f"Caveats ({len(warnings)})" if warnings else "Caveats")
        self.setVisible(True)
        self.logger.debug("Warning board shows %d warnings.", len(warnings))
        blocking = sum(1 for warning in warnings if self._severity(warning) is WarningSeverity.BLOCKING)
        if blocking:
            self.logger.warning("%d blocking caveats limit the rise drivers analysis.", blocking)

    def show_error(self, message: str) -> None:
        """Show an error stopping the analysis (storage, files).

        Args:
            message (str): The error.
        """
        self.logger.debug("Warning board shows the error %r.", message.splitlines()[0] if message else "")
        self._clear()
        severity = WarningSeverity.BLOCKING
        self._add(
            self.theme.warning_color(severity),
            self.theme.WARNING_SYMBOLS[severity],
            "Error",
            message.splitlines()[0] if message else "",
            f"<qt><p style='margin:0'><b>Error</b></p><p>{html.escape(message)}</p></qt>",
        )
        self.caption.setText("Caveats")
        self.setVisible(True)
        self.logger.debug("Warning board shows an error.")
