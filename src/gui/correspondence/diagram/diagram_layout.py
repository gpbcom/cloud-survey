from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional, Sequence

# Third Party Imports.
from PyQt6.QtCore import QPointF, QRectF

# First Party Imports.
from gui.correspondence.diagram.shapes.diagram_edge import DiagramEdge
from gui.correspondence.diagram.shapes.diagram_group import DiagramGroup
from gui.correspondence.diagram.shapes.diagram_pill import DiagramPill
from models.cloud.enums import CloudProvider
from models.correspondence.enums import CardinalityClass, MatchStrength, MemberRole
from models.correspondence.rows.concept_row import ConceptRow


class DiagramLayout:
    """Place the concepts of the correspondence diagram: one row per concept, one column per provider.

    Attributes:
        MARGIN (ClassVar[float]): The space around the diagram, in pixels.
        HEADER_HEIGHT (ClassVar[float]): The height of the column headers.
        GROUP_HEADER (ClassVar[float]): The height of the header of a domain.
        GROUP_GAP (ClassVar[float]): The space after the last row of a domain.
        ROW_GAP (ClassVar[float]): The space between two rows.
        PILL_HEIGHT (ClassVar[float]): The height of a pill.
        PILL_GAP (ClassVar[float]): The space between two stacked pills of a column.
        BAND_WIDTH (ClassVar[float]): The width of the coloured band of a domain.
        CONCEPT_WIDTH (ClassVar[float]): The width of the concept column.
        COLUMN_WIDTH (ClassVar[float]): The width of a provider column.
        COLUMN_GAP (ClassVar[float]): The space between two columns, where the connectors run (the largest one when
            the diagram fits a width).
        COMPACT_CONCEPT_WIDTH (ClassVar[float]): The width of the concept column beside many provider columns.
        MIN_COLUMN_WIDTH (ClassVar[float]): The narrowest provider column when the diagram fits a width.
        MIN_COLUMN_GAP (ClassVar[float]): The narrowest space between two columns when the diagram fits a width.
        NARROW_COLUMN (ClassVar[float]): The width below which a column is narrow (its header without flag).
        columns (List[CloudProvider]): The provider columns, in their order.
        strength (MatchStrength): Whether the partial services are shown.
        groups (List[DiagramGroup]): The domains, their header and band placed.
        pills (List[DiagramPill]): Every pill, row by row.
        edges (List[DiagramEdge]): Every connector, row by row.
        rows (Dict[int, QRectF]): The band of each concept row, by concept.
        headers (List[QRectF]): The header of the concept column, then of each provider column (drawn above the
            scrolled rows, in the coordinates of the header).
        concept_width (float): The width of the concept column.
        column_width (float): The width of a provider column.
        column_gap (float): The space between two columns.

        counts (Dict[CloudProvider, int]): The services shown in each provider column.
        width (float): The width of the diagram.
        height (float): The height of the diagram.
        logger (Logger): The layout logger.

    Notes:
        - A concept row is as tall as the column holding the most services of the concept: those services are
          stacked, centred on the row. A provider without a service of the concept gets an empty slot.
        - The connectors join every pill of a column to every pill of the next column holding a service (an empty
          slot is crossed), through a junction point when both columns hold several pills. Their class is the
          correspondence class of the two providers, the first connectors leave the concept pill with the class of
          the number of services of the first column.
    """

    MARGIN: ClassVar[float] = 16.0
    HEADER_HEIGHT: ClassVar[float] = 48.0
    GROUP_HEADER: ClassVar[float] = 30.0
    GROUP_GAP: ClassVar[float] = 12.0
    ROW_GAP: ClassVar[float] = 12.0
    PILL_HEIGHT: ClassVar[float] = 26.0
    PILL_GAP: ClassVar[float] = 5.0
    BAND_WIDTH: ClassVar[float] = 4.0
    CONCEPT_WIDTH: ClassVar[float] = 220.0
    COLUMN_WIDTH: ClassVar[float] = 200.0
    COLUMN_GAP: ClassVar[float] = 64.0
    COMPACT_CONCEPT_WIDTH: ClassVar[float] = 150.0
    MIN_COLUMN_WIDTH: ClassVar[float] = 18.0
    MIN_COLUMN_GAP: ClassVar[float] = 6.0
    NARROW_COLUMN: ClassVar[float] = 90.0

    def __init__(
        self,
        groups: Sequence[DiagramGroup],
        columns: Sequence[CloudProvider],
        strength: MatchStrength = MatchStrength.ANY,
        logger: Optional[Logger] = None,
        width: Optional[float] = None,
    ) -> None:
        """Place the groups of concepts.

        Args:
            groups (Sequence[DiagramGroup]): The concepts, grouped by domain, in their order.
            columns (Sequence[CloudProvider]): The provider columns, in their order.
            strength (MatchStrength): Whether the partial services are shown.
            logger (Optional[Logger]): The layout logger.
            width (Optional[float]): The width the columns share (the diagram fills it), the default column widths
                when `None`.
        """
        self.logger = logger if logger else getLogger(__name__)
        self.columns = list(columns)
        self.strength = strength
        self.groups = list(groups)
        self.pills: List[DiagramPill] = []
        self.edges: List[DiagramEdge] = []
        self.rows: Dict[int, QRectF] = {}
        self.counts: Dict[CloudProvider, int] = {provider: 0 for provider in self.columns}
        count = max(len(self.columns), 1)
        fixed = 2 * self.MARGIN + self.BAND_WIDTH + 8
        self.concept_width = self.CONCEPT_WIDTH
        if width is not None and (width - fixed - self.CONCEPT_WIDTH) / count * 0.75 < self.NARROW_COLUMN:
            self.concept_width = self.COMPACT_CONCEPT_WIDTH
        self.column_width, self.column_gap = self.COLUMN_WIDTH, self.COLUMN_GAP
        if width is not None:
            share = (width - fixed - self.concept_width) / count
            self.column_gap = max(self.MIN_COLUMN_GAP, min(self.COLUMN_GAP, share * 0.25))
            self.column_width = max(self.MIN_COLUMN_WIDTH, share - self.column_gap)
        self.width = fixed + self.concept_width + len(self.columns) * (self.column_gap + self.column_width)
        self.headers = [QRectF(self._column_x(0), 6, self._column_width(0), self.HEADER_HEIGHT - 12)]
        self.headers += [
            QRectF(self._column_x(index + 1), 6, self.column_width, self.HEADER_HEIGHT - 12)
            for index in range(len(self.columns))
        ]
        self.height = self._place()
        self.logger.debug(
            "Correspondence diagram laid out: %d rows, %d pills, %d connectors.",
            len(self.rows),
            len(self.pills),
            len(self.edges),
        )

    ############################
    # Internal Helpers Methods #
    ############################

    def _column_x(self, index: int) -> float:
        """Get the left of a column.

        Args:
            index (int): The column, 0 for the concepts, then the providers.

        Returns:
            float: Its left, in pixels.
        """
        concepts = self.MARGIN + self.BAND_WIDTH + 8
        if index == 0:
            return concepts
        return concepts + self.concept_width + self.column_gap + (index - 1) * (self.column_width + self.column_gap)

    def _column_width(self, index: int) -> float:
        """Get the width of a column.

        Args:
            index (int): The column, 0 for the concepts, then the providers.

        Returns:
            float: Its width, in pixels.
        """
        return self.concept_width if index == 0 else self.column_width

    def _stack(self, top: float, height: float, count: int) -> List[float]:
        """Get the tops of pills stacked and centred in a row.

        Args:
            top (float): The top of the row.
            height (float): The height of the row.
            count (int): The number of pills.

        Returns:
            List[float]: The top of each pill.
        """
        stacked = count * self.PILL_HEIGHT + (count - 1) * self.PILL_GAP
        first = top + (height - stacked) / 2
        return [first + index * (self.PILL_HEIGHT + self.PILL_GAP) for index in range(count)]

    def _join(
        self,
        concept_id: int,
        kind: CardinalityClass,
        left: Optional[DiagramPill],
        start: QPointF,
        right: Optional[DiagramPill],
        end: Optional[QPointF] = None,
    ) -> None:
        """Add a connector between two pills, or between a pill and a junction point.

        Args:
            concept_id (int): The concept of the row.
            kind (CardinalityClass): The class colouring it.
            left (Optional[DiagramPill]): The pill it leaves, `None` when it leaves a junction point.
            start (QPointF): Where it starts.
            right (Optional[DiagramPill]): The pill it reaches, `None` when it reaches a junction point.
            end (Optional[QPointF]): Where it ends, the left of `right` by default.
        """
        members = [pill.member for pill in (left, right) if pill is not None and pill.member is not None]
        target = end if end is not None else QPointF(0, 0)
        if end is None and right is not None:
            target = QPointF(right.rect.left(), right.rect.center().y())
        self.edges.append(
            DiagramEdge(
                start,
                target,
                concept_id,
                kind,
                any(member.role is MemberRole.PARTIAL for member in members),
                min((member.confidence for member in members), default=100),
            )
        )

    def _merge(
        self, concept_id: int, kind: CardinalityClass, previous: List[DiagramPill], pills: List[DiagramPill]
    ) -> None:
        """Join two columns of several pills through a junction point in the gap (the lines merge, then fan out).

        Args:
            concept_id (int): The concept of the row.
            kind (CardinalityClass): The class colouring the connectors.
            previous (List[DiagramPill]): The pills of the left column.
            pills (List[DiagramPill]): The pills of the right column.
        """
        tops = [pill.rect.top() for pill in (*previous, *pills)]
        bottoms = [pill.rect.bottom() for pill in (*previous, *pills)]
        hub = QPointF((previous[0].rect.right() + pills[0].rect.left()) / 2, (min(tops) + max(bottoms)) / 2)
        for left in previous:
            self._join(concept_id, kind, left, QPointF(left.rect.right(), left.rect.center().y()), None, hub)
        for right in pills:
            self._join(concept_id, kind, None, hub, right)

    def _connect(self, concept: ConceptRow, columns: List[List[DiagramPill]]) -> None:
        """Join the pills of each column to those of the next column holding a service.

        Args:
            concept (ConceptRow): The concept of the row.
            columns (List[List[DiagramPill]]): The pills of the concept column, then of each provider column (empty
                for an empty slot).
        """
        previous, previous_provider = columns[0], None
        for pills in columns[1:]:
            if not pills:
                continue
            provider = pills[0].provider
            if previous_provider is None or provider is None:
                kind = ConceptRow.CLASSES.get(len(pills), CardinalityClass.MANY_TO_ONE)
            else:
                kind = concept.cardinality(previous_provider, provider, self.strength)
            if len(previous) > 1 and len(pills) > 1:
                self._merge(concept.id, kind, previous, pills)
            else:
                for left in previous:
                    for right in pills:
                        self._join(concept.id, kind, left, QPointF(left.rect.right(), left.rect.center().y()), right)
            previous, previous_provider = pills, provider

    def _row(self, concept: ConceptRow, top: float) -> float:
        """Place the pills and connectors of a concept.

        Args:
            concept (ConceptRow): The concept.
            top (float): The top of its row.

        Returns:
            float: The height of its row.
        """
        members = [concept.members_of(provider, self.strength) for provider in self.columns]
        tallest = max([1, *(len(services) for services in members)])
        height = tallest * self.PILL_HEIGHT + (tallest - 1) * self.PILL_GAP
        row_class = concept.row_class(self.columns, self.strength)
        concept_pill = DiagramPill(
            QRectF(self._column_x(0), self._stack(top, height, 1)[0], self.concept_width, self.PILL_HEIGHT),
            concept.id,
            concept.name,
            row_class,
        )
        placed: List[List[DiagramPill]] = [[concept_pill]]
        self.pills.append(concept_pill)
        for index, (provider, services) in enumerate(zip(self.columns, members, strict=True), start=1):
            left = self._column_x(index)
            if not services:
                slot = QRectF(left, self._stack(top, height, 1)[0], self.column_width, self.PILL_HEIGHT)
                self.pills.append(DiagramPill(slot, concept.id, "No equivalent", CardinalityClass.MISSING, provider))
                placed.append([])
                continue
            kind = ConceptRow.CLASSES.get(len(services), CardinalityClass.MANY_TO_ONE)
            column = [
                DiagramPill(
                    QRectF(left, pill_top, self.column_width, self.PILL_HEIGHT),
                    concept.id,
                    member.name,
                    kind,
                    provider,
                    member,
                )
                for pill_top, member in zip(self._stack(top, height, len(services)), services, strict=True)
            ]
            self.pills.extend(column)
            self.counts[provider] += len(services)
            placed.append(column)
        self._connect(concept, placed)
        self.rows[concept.id] = QRectF(self.MARGIN, top, self.width - 2 * self.MARGIN, height)
        return height

    def _place(self) -> float:
        """Place every group, row by row.

        Returns:
            float: The height of the diagram.
        """
        top = self.MARGIN
        if not self.groups:
            self.logger.debug("No row to place in the correspondence diagram.")
        for group in self.groups:
            group.header = QRectF(self.MARGIN, top, self.width - 2 * self.MARGIN, self.GROUP_HEADER)
            top += self.GROUP_HEADER
            band_top = top
            for concept in group.concepts:
                top += self._row(concept, top) + self.ROW_GAP
            group.band = QRectF(self.MARGIN, band_top, self.BAND_WIDTH, max(top - self.ROW_GAP - band_top, 0))
            top += self.GROUP_GAP
            self.logger.debug("Domain %r placed: %d rows.", group.title, len(group.concepts))
        return top + self.MARGIN

    ############################
    # Publicly Exposed Methods #
    ############################

    def pill_at(self, point: QPointF) -> Optional[DiagramPill]:
        """Find the pill under a point.

        Args:
            point (QPointF): The point, in diagram coordinates.

        Returns:
            Optional[DiagramPill]: The pill, `None` when the point is on none.
        """
        return next((pill for pill in self.pills if pill.rect.contains(point)), None)

    def concept_at(self, point: QPointF) -> Optional[int]:
        """Find the concept row under a point.

        Args:
            point (QPointF): The point, in diagram coordinates.

        Returns:
            Optional[int]: The concept of the row, `None` between the rows.
        """
        return next((concept_id for concept_id, band in self.rows.items() if band.contains(point)), None)
