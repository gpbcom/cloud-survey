from __future__ import annotations

from logging import Logger
from typing import List, Optional

import pytest
from pydantic import BaseModel
from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtWidgets import QDialog, QMessageBox
from pytestqt.qtbot import QtBot

from gui.catalogues.catalogue_tab import CatalogueTab
from gui.catalogues.catalogues_manager import CataloguesManager
from gui.catalogues.rows.curated_row_model import CuratedRowValues
from gui.catalogues.rows.row_editor_dialog import RowEditorDialog
from gui.storage_bridge.storage_loop import StorageLoop
from gui.theme import Theme
from models.curated.enums import CuratedFile, IdentifierKind, IdentifierStatus, RecordOrigin
from models.curated.launches.product_launch import ProductLaunch
from storage.storage import Storage

LAUNCH: CuratedRowValues = {
    "crawler": "azure",
    "name": "AI Anomaly Detector",
    "position": 0,
    "body": {"crawler": "azure", "name": "AI Anomaly Detector", "launched": "2019-03", "source": "https://x.y/a"},
    "note": None,
    "origin": "seed",
    "edited": False,
}


class FakeDialog:
    """A row form accepted at once with fixed values (`result`, set by each test)."""

    result: Optional[CuratedRowValues] = None

    def __init__(
        self, title: str, model: type[BaseModel], original: CuratedRowValues, logger: Optional[Logger] = None
    ) -> None:
        self.result_values = FakeDialog.result

    def exec(self) -> QDialog.DialogCode:
        return QDialog.DialogCode.Accepted


class TestRowEditorDialog:
    def test_a_valid_form_is_marked_as_changed_by_a_person(self, qtbot: QtBot) -> None:
        dialog = RowEditorDialog("Edit", ProductLaunch, LAUNCH)
        qtbot.addWidget(dialog)
        dialog.texts["note"].setPlainText("checked by hand")

        dialog.accept()

        assert dialog.result_values is not None
        assert dialog.result_values["note"] == "checked by hand"
        assert dialog.result_values["edited"] is True
        assert dialog.result_values["origin"] == RecordOrigin.USER.value

    @pytest.mark.parametrize(("body", "reason"), [("{", "Invalid JSON"), ("[]", "body")])
    def test_an_invalid_form_stays_open_with_the_reason(self, qtbot: QtBot, body: str, reason: str) -> None:
        dialog = RowEditorDialog("Edit", ProductLaunch, LAUNCH)
        qtbot.addWidget(dialog)
        dialog.texts["body"].setPlainText(body)

        dialog.accept()

        assert dialog.result_values is None
        assert reason in dialog.error_label.text()


@pytest.mark.db
class TestCataloguesManager:
    @pytest.fixture
    def manager(self, qtbot: QtBot, gui_loop: StorageLoop) -> CataloguesManager:
        window = CataloguesManager(Theme(), gui_loop)
        qtbot.addWidget(window)
        return window

    def tab(self, manager: CataloguesManager, file: CuratedFile) -> CatalogueTab:
        return next(editor for editor in manager.editors if editor.file is file)

    def select(self, tab: CatalogueTab, text: str) -> None:
        tab.filter_edit.setText(text)
        selection = tab.table.selectionModel()
        assert selection is not None
        selection.select(
            tab.model.index(0, 0),
            QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
        )

    async def test_each_section_is_listed(self, storage: Storage, manager: CataloguesManager, qtbot: QtBot) -> None:
        await storage.curated_seeder.seed()
        tab = self.tab(manager, CuratedFile.COMPANIES)

        manager.open_on(CuratedFile.COMPANIES)
        qtbot.waitUntil(lambda: tab.model.rowCount() >= 100, timeout=15_000)
        assert tab.accept_button.isHidden()
        tab.section_box.setCurrentIndex(1)

        assert tab.model.rowCount() > 100
        assert not tab.accept_button.isHidden()
        assert manager.tabs.currentWidget() is tab

    async def test_an_edit_is_written(
        self, storage: Storage, manager: CataloguesManager, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await storage.curated_seeder.seed()
        tab = self.tab(manager, CuratedFile.LAUNCHES)
        manager.open_on(CuratedFile.LAUNCHES)
        qtbot.waitUntil(lambda: tab.model.rowCount() > 1000, timeout=15_000)
        self.select(tab, "AI Anomaly Detector")
        row = tab.model.rows[tab.model.index_of(0) or 0]
        FakeDialog.result = {**row, "note": "checked by hand", "edited": True, "origin": "user"}
        monkeypatch.setattr("gui.catalogues.catalogue_tab.RowEditorDialog", FakeDialog)

        with qtbot.waitSignal(tab.edited, timeout=15_000):
            tab.edit()

        stored = await storage.launches.read(str(row["crawler"]), str(row["name"]))
        assert stored is not None
        assert stored.note == "checked by hand"
        assert stored.edited

    async def test_a_company_still_named_cannot_be_deleted(
        self, storage: Storage, manager: CataloguesManager, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await storage.curated_seeder.seed()
        tab = self.tab(manager, CuratedFile.CHRONOLOGY)
        manager.open_on(CuratedFile.CHRONOLOGY)
        qtbot.waitUntil(lambda: tab.part is not None, timeout=15_000)
        tab.section_box.setCurrentIndex(2)
        self.select(tab, "tymshare")
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
        messages: List[str] = []
        tab.message.connect(messages.append)

        tab.delete()
        qtbot.waitUntil(
            lambda: any("Refused" in message or "unknown companies" in message for message in messages), timeout=15_000
        )

        assert "tymshare" in {company.key for company in (await storage.catalogs.chronology()).companies}

    async def test_a_candidate_is_accepted(self, storage: Storage, manager: CataloguesManager, qtbot: QtBot) -> None:
        await storage.curated_seeder.seed()
        cik = await storage.company_identifiers.read("ibm", IdentifierKind.SEC_CIK, "0000051143")
        assert cik is not None
        await storage.company_identifiers.create(
            cik.model_copy(update={"value": "0000099999", "position": 9, "status": IdentifierStatus.CANDIDATE})
        )
        tab = self.tab(manager, CuratedFile.COMPANIES)
        manager.open_on(CuratedFile.COMPANIES)
        qtbot.waitUntil(lambda: tab.part is not None, timeout=15_000)
        tab.section_box.setCurrentIndex(1)
        self.select(tab, "0000099999")

        with qtbot.waitSignal(tab.edited, timeout=15_000):
            tab.accept_button.click()

        accepted = await storage.company_identifiers.read("ibm", IdentifierKind.SEC_CIK, "0000099999")
        assert accepted is not None
        assert accepted.status is IdentifierStatus.CONFIRMED
        assert accepted.edited
        assert (
            "0000099999" in next(c for c in (await storage.catalogs.companies()).companies if c.key == "ibm").sec_ciks
        )
