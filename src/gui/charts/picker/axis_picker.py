from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, FrozenSet, List, Optional, Tuple

# Third Party Imports.
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QResizeEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

# First Party Imports.
from analytics.series.axis_rules import AxisRules, GroupingOption, MetricOption
from analytics.series.chart_presets import ChartPresets
from gui.charts.common.chart_labels import ChartLabels
from gui.charts.picker.chart_kind_bar import ChartKindBar
from gui.charts.picker.options.option_combo import ComboOption, OptionCombo
from gui.charts.picker.options.options_menu import OptionsMenu
from models.storage.enums import DatasetKind
from models.trends.chart_axes import ChartAxes
from models.trends.enums import (
    ChartKind,
    ChartMetric,
    ChartScope,
    MatrixCell,
    OptionBlock,
    SeriesGrouping,
    ValueTransform,
)


class AxisPicker(QWidget):
    """Choose what a chart shows: its kind, its axes, its series and how their values are transformed.

    Attributes:
        WRAP_WIDTH (ClassVar[int]): The picker width below which the combo boxes move to a second row, in pixels.
        axes_changed (pyqtSignal): Emitted once with the new (valid) `ChartAxes` after each user change.
        labels (ChartLabels): The names of the options.
        scope (ChartScope): Where the chart is shown.
        rules (AxisRules): The chart rules: which options go together.
        presets (ChartPresets): The ready-made charts.
        current (ChartAxes): The chosen axes.
        available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.
        kind_bar (ChartKindBar): The chart kind buttons.
        y_box (OptionCombo): The y axis metric (the matrix cell metric for a heatmap).
        x_box (OptionCombo): The x axis metric (the matrix columns for a matrix chart).
        size_box (OptionCombo): The bubble size metric.
        by_box (OptionCombo): The series grouping (the matrix rows).
        facet_box (OptionCombo): The facet grouping: one chart, or one small chart per value (e.g. per provider).
        menu (OptionsMenu): The secondary options.
        options_button (QToolButton): Opens the secondary options, marked when one is not the default.
        captions (Dict[str, QLabel]): The caption of each combo box, by combo box name.
        fields (QWidget): The captions and combo boxes, on the first row or alone on a second one.
        top_row (QHBoxLayout): The chart kinds, the combo boxes (when wide enough) and the options.
        bottom_row (QHBoxLayout): The combo boxes, when the picker is narrow.
        wrapped (bool): Whether the combo boxes are on the second row.
        logger (Logger): The picker logger.

    Notes:
        - The primary options (y, x, size, grouping, facets) are always in view, the secondary ones in the options
          menu.
        - The options which cannot be chosen with the others are shown disabled, with why as tooltip, and every
          change is repaired by the rules: the picker never produces an invalid chart.
        - A missing dataset only disables the options needing it: the chosen chart is kept (and shows what to crawl
          first), so that it comes back as soon as the data is stored.
        - The matrix charts reuse the boxes: the rows in `y_box`, the columns in `x_box`, the cells in `by_box`.
        - On a narrow picker, the combo boxes move to a second row rather than squeezing each other.
    """

    WRAP_WIDTH: ClassVar[int] = 960

    axes_changed = pyqtSignal(object)

    def __init__(self, labels: ChartLabels, scope: ChartScope, logger: Optional[Logger] = None) -> None:
        """Build the picker, showing the default ready-made chart of the scope.

        Args:
            labels (ChartLabels): The names of the options.
            scope (ChartScope): Where the chart is shown.
            logger (Optional[Logger]): The picker logger.
        """
        super().__init__()
        self.logger = logger if logger else getLogger(__name__)
        self.labels = labels
        self.scope = scope
        self.rules = AxisRules(self.logger)
        self.presets = ChartPresets(self.logger)
        self.current = self.presets.default(scope)
        self.available: Optional[FrozenSet[DatasetKind]] = None
        self.kind_bar = ChartKindBar(self.logger)
        self.y_box, self.x_box = OptionCombo("Y axis", self.logger), OptionCombo("X axis", self.logger)
        self.size_box, self.by_box = OptionCombo("Bubble size", self.logger), OptionCombo("Series", self.logger)
        self.facet_box = OptionCombo("Per", self.logger)
        self.menu = OptionsMenu(self.logger)
        self.options_button = QToolButton()
        self.options_button.setObjectName("chartTool")
        self.options_button.setMenu(self.menu)
        self.options_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.options_button.setAccessibleName("Chart options")
        self.captions: Dict[str, QLabel] = {}
        self.fields = QWidget()
        fields = QHBoxLayout(self.fields)
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(8)
        for name, box in self._boxes():
            caption = QLabel()
            caption.setObjectName("muted")
            caption.setBuddy(box)
            self.captions[name] = caption
            fields.addWidget(caption)
            fields.addWidget(box)
            box.currentIndexChanged.connect(lambda index: self._on_changed())
        self.top_row, self.bottom_row = QHBoxLayout(), QHBoxLayout()
        self.top_row.setSpacing(16)
        self.top_row.addWidget(self.kind_bar)
        self.top_row.addWidget(self.fields)
        self.top_row.addStretch(1)
        self.top_row.addWidget(self.options_button)
        self.bottom_row.addStretch(1)
        rows = QVBoxLayout(self)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(8)
        rows.addLayout(self.top_row)
        rows.addLayout(self.bottom_row)
        self.wrapped = False
        self.kind_bar.kind_changed.connect(lambda value: self._on_changed())
        self.menu.changed.connect(self._on_changed)
        self._fill()

    ############################
    # Internal Helpers Methods #
    ############################

    def _boxes(self) -> List[Tuple[str, OptionCombo]]:
        """Get the combo boxes, by name.

        Returns:
            List[Tuple[str, OptionCombo]]: The y, x, size, grouping and facet boxes.
        """
        return [
            ("y", self.y_box),
            ("x", self.x_box),
            ("size", self.size_box),
            ("by", self.by_box),
            ("per", self.facet_box),
        ]

    def _reason(self, block: Optional[OptionBlock]) -> Optional[str]:
        """Explain why an option is blocked.

        Args:
            block (Optional[OptionBlock]): Why it is blocked, `None` when it is not.

        Returns:
            Optional[str]: The explanation, `None` when the option can be chosen.
        """
        return self.labels.BLOCK_LABELS[block] if block is not None else None

    def _metric_options(self, options: List[MetricOption]) -> List[ComboOption]:
        """Name metric options.

        Args:
            options (List[MetricOption]): The metrics and why each is blocked.

        Returns:
            List[ComboOption]: The value, label and blocking reason of each metric.
        """
        return [
            (metric.value, self.labels.metric_label(metric, self.scope), self._reason(block))
            for metric, block in options
        ]

    def _grouping_options(self, options: List[GroupingOption]) -> List[ComboOption]:
        """Name grouping options.

        Args:
            options (List[GroupingOption]): The groupings and why each is blocked.

        Returns:
            List[ComboOption]: The value, label and blocking reason of each grouping.
        """
        return [
            (grouping.value, self.labels.GROUPING_LABELS[grouping], self._reason(block)) for grouping, block in options
        ]

    def _facet_options(self, axes: ChartAxes) -> List[ComboOption]:
        """Name the facet options.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            List[ComboOption]: One chart (empty value) first, then one small chart per value of each grouping.
        """
        return [
            (
                grouping.value if grouping else "",
                f"Per {self.labels.GROUPING_LABELS[grouping].lower()}" if grouping else "One chart",
                self._reason(block),
            )
            for grouping, block in self.rules.facet_options(axes)
        ]

    def _captions(self, axes: ChartAxes) -> Dict[str, str]:
        """Name the combo boxes for the chart kind.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            Dict[str, str]: The caption of each combo box shown.
        """
        match axes.chart:
            case ChartKind.HEATMAP:
                return {"y": "Rows", "x": "Columns", "by": "Cells"}
            case ChartKind.MIX:
                return {"y": "Rows", "x": "Columns"}
            case ChartKind.BUBBLE:
                return {"y": "Y", "x": "X", "size": "Size", "by": "By"}
            case _:
                return {"y": "Y", "x": "X", "by": "By", "per": "Charts"}

    def _is_default(self, axes: ChartAxes) -> bool:
        """Tell whether the secondary options change what the values mean.

        Args:
            axes (ChartAxes): The chart axes.

        Returns:
            bool: Whether the values are raw, without forecast, derivative nor logarithmic axes (the number of series
                aside).
        """
        return axes.transform is ValueTransform.RAW and not axes.forecast and not axes.log_scale and not axes.derivative

    def _wrap(self, wrapped: bool) -> None:
        """Move the combo boxes to a second row, or back to the first one.

        Args:
            wrapped (bool): Whether the combo boxes go to the second row.
        """
        if wrapped == self.wrapped:
            return
        self.logger.debug("Chart picker laid out on %s.", "two rows" if wrapped else "one row")
        self.wrapped = wrapped
        if wrapped:
            self.top_row.removeWidget(self.fields)
            self.bottom_row.insertWidget(0, self.fields)
        else:
            self.bottom_row.removeWidget(self.fields)
            self.top_row.insertWidget(1, self.fields)

    def _fill(self) -> None:
        """Show the chosen axes and the options going with them, without emitting a change."""
        axes, available = self.current, self.available
        self.logger.debug(
            "Chart picker showing a %s chart of %s in the %s scope.", axes.chart.value, axes.y.value, self.scope.value
        )
        if available is None:
            self.logger.debug("Stored datasets unknown: no option blocked for a missing dataset.")
        kinds = [
            (kind.value, self.labels.KIND_LABELS[kind], self.labels.KIND_TIPS[kind])
            for kind in self.rules.kinds(self.scope)
        ]
        self.kind_bar.set_kinds(kinds, axes.chart.value)
        captions = self._captions(axes)
        if axes.chart.is_matrix:
            cells: List[ComboOption] = [
                (cell.value, self.labels.CELL_LABELS[cell], None) for cell in self.rules.cell_options(axes)
            ]
            self.y_box.set_options(self._grouping_options(self.rules.groupings(axes)), axes.series_by.value)
            self.x_box.set_options(self._grouping_options(self.rules.column_options(axes)), axes.columns.value)
            self.by_box.set_options(cells, axes.cell.value)
        else:
            self.y_box.set_options(self._metric_options(self.rules.y_options(axes, available)), axes.y.value)
            self.x_box.set_options(self._metric_options(self.rules.x_options(axes, available)), axes.x.value)
            sizes = self.rules.size_options(axes, available) if axes.chart is ChartKind.BUBBLE else []
            self.size_box.set_options(self._metric_options(sizes), axes.size.value if axes.size else "")
            self.by_box.set_options(self._grouping_options(self.rules.groupings(axes)), axes.series_by.value)
            self.facet_box.set_options(self._facet_options(axes), axes.facet_by.value if axes.facet_by else "")
        for name, box in self._boxes():
            shown = name in captions
            self.captions[name].setText(captions.get(name, ""))
            self.captions[name].setVisible(shown)
            box.setVisible(shown)
            box.setAccessibleName(captions.get(name, name))
        transforms = [
            (transform.value, self.labels.TRANSFORM_LABELS[transform], self._reason(block))
            for transform, block in self.rules.transforms(axes)
        ]
        self.menu.set_state(
            transforms,
            axes.transform.value,
            axes.top,
            axes.forecast,
            self._reason(self.rules.forecastable(axes)),
            axes.log_scale if axes.chart is ChartKind.BUBBLE else None,
            axes.derivative if self.rules.derivable(axes) is None else None,
        )
        self.options_button.setText("⚙ Options" if self._is_default(axes) else "⚙ Options •")
        self.options_button.setToolTip(
            "Values, number of series, forecast, rate of change"
            if self._is_default(axes)
            else "Some options differ from the defaults"
        )

    def _read(self) -> ChartAxes:
        """Read the options chosen in the widgets.

        Returns:
            ChartAxes: The chosen axes, maybe invalid, no longer naming a ready-made chart.
        """
        axes = self.current
        kind = ChartKind(self.kind_bar.kind() or axes.chart.value)
        if kind is not axes.chart:
            self.logger.debug("Chart kind changed from %s to %s.", axes.chart.value, kind.value)
            return axes.model_copy(update={"chart": kind, "preset": None})
        size, facet = self.size_box.value(), self.facet_box.value()
        matrix = kind.is_matrix
        return ChartAxes(
            scope=axes.scope,
            chart=kind,
            x=axes.x if matrix else ChartMetric(self.x_box.value() or axes.x.value),
            y=axes.y if matrix else ChartMetric(self.y_box.value() or axes.y.value),
            size=ChartMetric(size) if size and not matrix else axes.size,
            series_by=SeriesGrouping((self.y_box if matrix else self.by_box).value() or axes.series_by.value),
            facet_by=SeriesGrouping(facet) if facet and not matrix else None,
            columns=SeriesGrouping(self.x_box.value() or axes.columns.value) if matrix else axes.columns,
            cell=MatrixCell(self.by_box.value() or axes.cell.value) if matrix else axes.cell,
            transform=ValueTransform(self.menu.transform() or axes.transform.value),
            forecast=self.menu.forecast(),
            log_scale=self.menu.log_scale(),
            derivative=self.menu.derivative(),
            top=self.menu.top(),
        )

    def _on_changed(self) -> None:
        """Repair the options chosen by the user, show them and report the new axes."""
        chosen = self._read()
        repaired = self.rules.repair(chosen)
        if repaired != chosen:
            self.logger.debug("Chosen chart options repaired to a valid chart.")
        if repaired == self.current:
            self.logger.debug("Chart options unchanged after the repair.")
            self._fill()
            return
        self.current = repaired
        self._fill()
        self.logger.debug("Chart axes chosen: %s.", repaired)
        self.axes_changed.emit(repaired)

    ############################
    # Publicly Exposed Methods #
    ############################

    def axes(self) -> ChartAxes:
        """Get the chosen axes.

        Returns:
            ChartAxes: The axes, valid.
        """
        return self.current

    def set_axes(self, axes: ChartAxes) -> None:
        """Show axes (e.g. restored or ready-made), repaired when needed, without emitting a change.

        Args:
            axes (ChartAxes): The axes.
        """
        scoped = axes.model_copy(update={"scope": self.scope})
        self.current = self.rules.repair(scoped)
        if self.current != scoped:
            self.logger.warning(
                "Chart axes repaired before being shown: they were not valid in the %s scope.", self.scope.value
            )
        self.logger.debug("Chart axes shown: a %s chart of %s.", self.current.chart.value, self.current.y.value)
        self._fill()

    def set_available(self, available: Optional[FrozenSet[DatasetKind]]) -> None:
        """Tell which datasets are stored, disabling the options needing the others.

        Args:
            available (Optional[FrozenSet[DatasetKind]]): The stored datasets, `None` when unknown.
        """
        self.logger.debug(
            "Stored datasets of the chart picker: %s.",
            sorted(dataset.value for dataset in available) if available is not None else "unknown",
        )
        self.available = available
        self._fill()

    def resizeEvent(self, event: Optional[QResizeEvent]) -> None:
        """Lay the combo boxes out on one or two rows, for the picker width (Qt override).

        Args:
            event (Optional[QResizeEvent]): The resize event.
        """
        self._wrap(self.width() < self.WRAP_WIDTH)
        super().resizeEvent(event)
