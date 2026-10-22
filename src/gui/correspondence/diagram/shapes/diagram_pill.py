from __future__ import annotations

# Standard Library Imports.
from typing import Optional

# Third Party Imports.
from PyQt6.QtCore import QRectF

# First Party Imports.
from models.cloud.enums import CloudProvider
from models.correspondence.enums import CardinalityClass
from models.correspondence.rows.concept_member import ConceptMember


class DiagramPill:
    """A rounded box of the correspondence diagram: a concept, a service, or the empty slot of a missing one.

    Attributes:
        rect (QRectF): Where it is drawn, in diagram coordinates.
        concept_id (int): The concept of its row.
        text (str): What it reads.
        kind (CardinalityClass): The class colouring it (`missing` for an empty slot).
        provider (Optional[CloudProvider]): The provider column it sits in, `None` for the concept column.
        member (Optional[ConceptMember]): The service it stands for, `None` for a concept or an empty slot.
    """

    def __init__(
        self,
        rect: QRectF,
        concept_id: int,
        text: str,
        kind: CardinalityClass,
        provider: Optional[CloudProvider] = None,
        member: Optional[ConceptMember] = None,
    ) -> None:
        """Initialize the pill.

        Args:
            rect (QRectF): Where it is drawn.
            concept_id (int): The concept of its row.
            text (str): What it reads.
            kind (CardinalityClass): The class colouring it.
            provider (Optional[CloudProvider]): The provider column it sits in.
            member (Optional[ConceptMember]): The service it stands for.
        """
        self.rect = rect
        self.concept_id = concept_id
        self.text = text
        self.kind = kind
        self.provider = provider
        self.member = member

    ############################
    # Publicly Exposed Methods #
    ############################

    def is_concept(self) -> bool:
        """Tell whether the pill names the concept of its row.

        Returns:
            bool: Whether it sits in the concept column.
        """
        return self.provider is None

    def is_gap(self) -> bool:
        """Tell whether the pill is the empty slot of a provider without a service of the concept.

        Returns:
            bool: Whether no service stands behind it.
        """
        return self.provider is not None and self.member is None
