from __future__ import annotations

# Standard Library Imports.
import html
from logging import Logger, getLogger
from typing import ClassVar, Dict, List, Optional

# Third Party Imports.
from PyQt6.QtCore import Qt, QUrl, pyqtBoundSignal, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout

# First Party Imports.
from gui.theme import Theme
from models.cloud.enums import CloudProvider
from models.correspondence.enums import ConceptSource, MemberRole
from models.correspondence.rows.concept_member import ConceptMember
from models.correspondence.rows.concept_row import ConceptRow


class ConceptDetails(QFrame):
    """The details panel of the Correspondences tab: a service concept and its services, grouped by provider.

    Attributes:
        PLACEHOLDER (ClassVar[str]): What the panel says without a selected concept.
        rename_requested (pyqtSignal): Emitted with the concept to rename.
        merge_requested (pyqtSignal): Emitted with the concept to merge into another.
        add_requested (pyqtSignal): Emitted with the concept to file a service under.
        delete_requested (pyqtSignal): Emitted with the concept to delete.
        rematch_requested (pyqtSignal): Emitted with the category to match again with the language model.
        unlink_requested (pyqtSignal): Emitted with the concept and the service to remove from it.
        role_requested (pyqtSignal): Emitted with the concept, the service and its new role.
        theme (Theme): The application theme.
        concept (Optional[ConceptRow]): The concept shown.
        title_label (QLabel): The name of the concept.
        path_label (QLabel): Its taxonomy category, and who created it.
        description_label (QLabel): What it stands for.
        members_label (QLabel): Its services, by provider, with their role, confidence and actions.
        rename_button, merge_button, add_button, delete_button, rematch_button (QPushButton): The concept actions.
        logger (Logger): The panel logger.

    Notes:
        The changes made here are set by hand: the language model never changes them, and a removed service is never
        filed under the concept again.
    """

    PLACEHOLDER: ClassVar[str] = "Select a concept in the diagram to see its services and edit it."

    rename_requested = pyqtSignal(int)
    merge_requested = pyqtSignal(int)
    add_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)
    rematch_requested = pyqtSignal(str)
    unlink_requested = pyqtSignal(int, int)
    role_requested = pyqtSignal(int, int, str)

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Build the panel, empty.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The panel logger.
        """
        super().__init__()
        self.setObjectName("details")
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)
        self.concept: Optional[ConceptRow] = None
        self.title_label = QLabel()
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(True)
        self.path_label = QLabel()
        self.path_label.setObjectName("muted")
        self.path_label.setWordWrap(True)
        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.members_label = QLabel()
        self.members_label.setWordWrap(True)
        self.members_label.setTextFormat(Qt.TextFormat.RichText)
        self.members_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.members_label.linkActivated.connect(self._on_link)
        self.rename_button = QPushButton("Rename…")
        self.merge_button = QPushButton("Merge into…")
        self.add_button = QPushButton("Add a service…")
        self.delete_button = QPushButton("Delete")
        self.rematch_button = QPushButton("Match the category again with AI")
        self.rematch_button.setToolTip("Forget the matches of the concept's category: the next AI run matches it again")
        buttons = QGridLayout()
        buttons.addWidget(self.rename_button, 0, 0)
        buttons.addWidget(self.merge_button, 0, 1)
        buttons.addWidget(self.add_button, 1, 0)
        buttons.addWidget(self.delete_button, 1, 1)
        buttons.addWidget(self.rematch_button, 2, 0, 1, 2)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        for label in (self.title_label, self.path_label, self.description_label):
            layout.addWidget(label)
        layout.addLayout(buttons)
        layout.addWidget(self.members_label, 1)
        self.rename_button.clicked.connect(lambda: self._emit_concept(self.rename_requested))
        self.merge_button.clicked.connect(lambda: self._emit_concept(self.merge_requested))
        self.add_button.clicked.connect(lambda: self._emit_concept(self.add_requested))
        self.delete_button.clicked.connect(lambda: self._emit_concept(self.delete_requested))
        self.rematch_button.clicked.connect(self._on_rematch)
        self.show_concept(None)
        self.logger.debug("Concept details built.")

    ############################
    # Internal Helpers Methods #
    ############################

    def _emit_concept(self, signal: pyqtBoundSignal) -> None:
        """Tell an action on the shown concept.

        Args:
            signal (pyqtBoundSignal): The signal of the action.
        """
        if self.concept is not None:
            signal.emit(self.concept.id)

    def _on_rematch(self) -> None:
        """Ask for the category of the shown concept to be matched again."""
        if self.concept is not None and self.concept.node_slug:
            self.rematch_requested.emit(self.concept.node_slug)

    def _on_link(self, link: str) -> None:
        """Run an action of the services list: open a page, change a role, remove a service.

        Args:
            link (str): The link: `open:<url>`, `role:<product>:<role>` or `remove:<product>`.
        """
        action, _, value = link.partition(":")
        if self.concept is None:
            return
        match action:
            case "open":
                QDesktopServices.openUrl(QUrl(value))
            case "role":
                product, _, role = value.partition(":")
                self.role_requested.emit(self.concept.id, int(product), role)
            case "remove":
                self.unlink_requested.emit(self.concept.id, int(value))
            case _:
                self.logger.warning("Unknown action of the concept details: %r.", link)

    def _member(self, member: ConceptMember, editable: bool) -> str:
        """Write a service of the concept.

        Args:
            member (ConceptMember): The service.
            editable (bool): Whether its actions are offered (not for a taxonomy category).

        Returns:
            str: Rich text: its name (a link to its page), its role, its confidence or source, and its actions.
        """
        muted = self.theme.TEXT_MUTED
        name = html.escape(member.name)
        if member.url:
            link = html.escape(f"open:{member.url}", quote=True)
            name = f'<a href="{link}" style="color:{self.theme.TEXT}; text-decoration:none;">{name}</a>'
        if member.deleted:
            name = f"<s>{name}</s>"
        if not editable:
            return f"&nbsp;&nbsp;{name}"
        partial = member.role is MemberRole.PARTIAL
        role = "partial" if partial else "equivalent"
        origin = "set by hand ✎" if member.source is ConceptSource.USER else f"AI {member.confidence}%"
        other = MemberRole.EQUIVALENT if partial else MemberRole.PARTIAL
        actions = (
            f'<a href="role:{member.product_id}:{other.value}" style="color:{self.theme.ACCENT};">'
            f"mark {other.value}</a>"
            f' · <a href="remove:{member.product_id}" style="color:{self.theme.WARNING};">remove</a>'
        )
        return (
            f"&nbsp;&nbsp;{name} <span style='color:{muted};'>({role}, {origin})</span><br>"
            f"&nbsp;&nbsp;&nbsp;&nbsp;<span style='font-size:small;'>{actions}</span>"
        )

    def _members(self, concept: ConceptRow, editable: bool) -> str:
        """Write the services of a concept, grouped by provider.

        Args:
            concept (ConceptRow): The concept.
            editable (bool): Whether the actions of the services are offered.

        Returns:
            str: Rich text: one block per provider (its colour and its name), then its services.
        """
        by_provider: Dict[CloudProvider, List[ConceptMember]] = {}
        for member in concept.members:
            by_provider.setdefault(member.provider, []).append(member)
        blocks: List[str] = []
        for provider in sorted(by_provider, key=lambda provider: self.theme.provider_label(provider).casefold()):
            color = self.theme.PROVIDER_COLORS[provider]
            lines = [f"<span style='color:{color};'>●</span> <b>{html.escape(self.theme.provider_label(provider))}</b>"]
            lines += [self._member(member, editable) for member in concept.members_of(provider)]
            blocks.append("<br>".join(lines))
        return "<br><br>".join(blocks) if blocks else f"<span style='color:{self.theme.TEXT_MUTED};'>No service</span>"

    ############################
    # Publicly Exposed Methods #
    ############################

    def show_concept(self, concept: Optional[ConceptRow], path: str = "", editable: bool = True) -> None:
        """Show a concept, or the placeholder.

        Args:
            concept (Optional[ConceptRow]): The concept, `None` for none.
            path (str): The English path of its taxonomy category.
            editable (bool): Whether it is a stored concept (its actions offered), `False` for a taxonomy category.
        """
        self.concept = concept if editable else None
        for button in (self.rename_button, self.merge_button, self.add_button, self.delete_button):
            button.setEnabled(concept is not None and editable)
        self.rematch_button.setEnabled(concept is not None and bool(concept.node_slug) and editable)
        if concept is None:
            self.title_label.setText("No concept selected")
            self.path_label.setText("")
            self.description_label.setText(self.PLACEHOLDER)
            self.members_label.setText("")
            return
        providers = len({member.provider for member in concept.members})
        origin = "created by hand" if concept.source is ConceptSource.USER else "found by the AI"
        if not editable:
            origin = "taxonomy category, not matched by the AI"
        edited = ", edited" if concept.edited and concept.source is ConceptSource.LLM else ""
        self.title_label.setText(concept.name)
        self.path_label.setText(f"{path or 'No category'} · {origin}{edited} · {providers} providers")
        self.description_label.setText(concept.description)
        self.members_label.setText(self._members(concept, editable))
        self.logger.debug("Concept %r shown with %d services.", concept.name, len(concept.members))
