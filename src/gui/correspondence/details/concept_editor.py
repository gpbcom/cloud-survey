from __future__ import annotations

# Standard Library Imports.
from logging import Logger, getLogger
from typing import Optional, Sequence, Tuple

# Third Party Imports.
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

# First Party Imports.
from gui.theme import Theme
from models.correspondence.enums import MemberRole
from models.correspondence.rows.concept_member import ConceptMember
from models.correspondence.rows.concept_row import ConceptRow


class ConceptEditor:
    """The small dialogs editing the service concepts by hand: name, merge target, added service, confirmation.

    Attributes:
        theme (Theme): The application theme.
        logger (Logger): The editor logger.
    """

    def __init__(self, theme: Theme, logger: Optional[Logger] = None) -> None:
        """Initialize the editor.

        Args:
            theme (Theme): The application theme.
            logger (Optional[Logger]): The editor logger.
        """
        self.theme = theme
        self.logger = logger if logger else getLogger(__name__)

    ############################
    # Internal Helpers Methods #
    ############################

    def _dialog(self, parent: QWidget, title: str) -> Tuple[QDialog, QVBoxLayout, QDialogButtonBox]:
        """Build an empty dialog with OK and Cancel.

        Args:
            parent (QWidget): The parent widget.
            title (str): The window title.

        Returns:
            Tuple[QDialog, QVBoxLayout, QDialogButtonBox]: The dialog, its layout, its buttons (added last by the
                caller).
        """
        dialog = QDialog(parent)
        dialog.setWindowTitle(title)
        dialog.setMinimumWidth(460)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        return dialog, QVBoxLayout(dialog), buttons

    def _filter_list(self, items: QListWidget, text: str) -> None:
        """Hide the entries of a list not containing a text.

        Args:
            items (QListWidget): The list.
            text (str): The text, case-insensitive.
        """
        wanted = text.strip().casefold()
        for row in range(items.count()):
            item = items.item(row)
            if item is not None:
                item.setHidden(bool(wanted) and wanted not in item.text().casefold())

    ############################
    # Publicly Exposed Methods #
    ############################

    def ask_name(self, parent: QWidget, title: str, name: str = "", description: str = "") -> Optional[Tuple[str, str]]:
        """Ask for the name and the description of a concept.

        Args:
            parent (QWidget): The parent widget.
            title (str): The window title.
            name (str): The current name.
            description (str): The current description.

        Returns:
            Optional[Tuple[str, str]]: The name and the description, `None` when cancelled or left without a name.
        """
        dialog, layout, buttons = self._dialog(parent, title)
        name_box, description_box = QLineEdit(name), QLineEdit(description)
        name_box.setPlaceholderText("e.g. Managed Kubernetes")
        description_box.setPlaceholderText("What the concept stands for, in one line")
        form = QFormLayout()
        form.addRow("Name", name_box)
        form.addRow("Description", description_box)
        layout.addLayout(form)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or not name_box.text().strip():
            return None
        return name_box.text().strip(), description_box.text().strip()

    def pick_concept(self, parent: QWidget, concepts: Sequence[ConceptRow], excluded: int) -> Optional[int]:
        """Ask for the concept another one is merged into.

        Args:
            parent (QWidget): The parent widget.
            concepts (Sequence[ConceptRow]): The concepts offered.
            excluded (int): The concept being merged (not offered).

        Returns:
            Optional[int]: The chosen concept, `None` when cancelled.
        """
        dialog, layout, buttons = self._dialog(parent, "Merge into another concept")
        search = QLineEdit()
        search.setPlaceholderText("Find a concept…")
        items = QListWidget()
        for concept in sorted(concepts, key=lambda row: row.name.casefold()):
            if concept.id == excluded:
                continue
            item = QListWidgetItem(f"{concept.name}  ({len(concept.members)} services)")
            item.setData(Qt.ItemDataRole.UserRole, concept.id)
            items.addItem(item)
        search.textChanged.connect(lambda text: self._filter_list(items, text))
        layout.addWidget(QLabel("The services of the concept move to the chosen one, then the concept is deleted."))
        layout.addWidget(search)
        layout.addWidget(items, 1)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted or items.currentItem() is None:
            return None
        current = items.currentItem()
        return int(current.data(Qt.ItemDataRole.UserRole)) if current is not None else None

    def pick_service(self, parent: QWidget, services: Sequence[ConceptMember]) -> Optional[Tuple[int, MemberRole]]:
        """Ask for a service to file under a concept, and its role.

        Args:
            parent (QWidget): The parent widget.
            services (Sequence[ConceptMember]): The services offered (those of the concept's category).

        Returns:
            Optional[Tuple[int, MemberRole]]: The product and its role, `None` when cancelled.
        """
        dialog, layout, buttons = self._dialog(parent, "Add a service to the concept")
        search = QLineEdit()
        search.setPlaceholderText("Find a service or a provider…")
        items = QListWidget()
        for service in services:
            item = QListWidgetItem(
                self.theme.provider_icon(service.provider),
                f"{self.theme.PROVIDER_SHORT_LABELS[service.provider]} · {service.name}",
            )
            item.setToolTip(service.description)
            item.setData(Qt.ItemDataRole.UserRole, service.product_id)
            items.addItem(item)
        role = QComboBox()
        role.addItem("Equivalent", MemberRole.EQUIVALENT.value)
        role.addItem("Partial", MemberRole.PARTIAL.value)
        search.textChanged.connect(lambda text: self._filter_list(items, text))
        layout.addWidget(search)
        layout.addWidget(items, 1)
        layout.addWidget(role)
        layout.addWidget(buttons)
        current = items.currentItem() if dialog.exec() == QDialog.DialogCode.Accepted else None
        if current is None:
            return None
        return int(current.data(Qt.ItemDataRole.UserRole)), MemberRole(role.currentData())

    def confirm(self, parent: QWidget, question: str) -> bool:
        """Ask for a confirmation.

        Args:
            parent (QWidget): The parent widget.
            question (str): The question.

        Returns:
            bool: Whether the person confirmed.
        """
        answer = QMessageBox.question(parent, "Correspondences", question)
        return answer == QMessageBox.StandardButton.Yes
