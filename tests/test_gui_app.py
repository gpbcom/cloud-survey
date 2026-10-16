from __future__ import annotations

import os
import runpy
from collections.abc import Iterator
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication

import gui.app as app_module


@pytest.fixture(autouse=True)
def isolated_app(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_logging: None
) -> Iterator[None]:
    """Run in a temporary directory, without event loop, and restore the application look afterwards."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(qapp, "exec", lambda: 0)
    stylesheet, palette = qapp.styleSheet(), qapp.palette()
    yield
    for widget in qapp.topLevelWidgets():
        widget.close()
    qapp.setStyleSheet(stylesheet)
    qapp.setPalette(palette)


def test_main_shows_the_window(qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    setup_logging = MagicMock()
    monkeypatch.setattr(app_module, "setup_logging", setup_logging)

    assert app_module.main() == 0

    setup_logging.assert_called_once_with()
    windows = [
        widget for widget in qapp.topLevelWidgets() if isinstance(widget, app_module.MainWindow) and widget.isVisible()
    ]
    assert len(windows) == 1
    assert windows[0].store.output_dir == Path("output")
    assert (tmp_path / "output").is_dir()
    assert qapp.applicationName() == "Cloud Catalogue Explorer"


def test_main_creates_the_application_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    created: List[FakeApplication] = []

    class FakeApplication:
        """Stand-in for `QApplication`, as no application exists yet."""

        def __init__(self, argv: List[str]) -> None:
            self.argv = argv
            self.setApplicationName = MagicMock()
            created.append(self)

        @staticmethod
        def instance() -> None:
            return None

        def exec(self) -> int:
            return 3

    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "setup_logging", MagicMock())
    monkeypatch.setattr(app_module, "Theme", MagicMock())
    monkeypatch.setattr(app_module, "MainWindow", MagicMock(TITLE="Cloud Catalogue Explorer"))

    assert app_module.main() == 3
    assert len(created) == 1
    created[0].setApplicationName.assert_called_once_with("Cloud Catalogue Explorer")


@pytest.mark.filterwarnings("ignore:'gui.app' found in sys.modules:RuntimeWarning")
def test_module_entrypoint_exits_with_the_application_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("logger.setup_logging", MagicMock())

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("gui.app", run_name="__main__")

    assert exc_info.value.code == 0


@pytest.mark.parametrize(("configured", "expected"), [(None, "generic"), ("gtk3", "gtk3")])
def test_platform_theme(monkeypatch: pytest.MonkeyPatch, configured: Optional[str], expected: str) -> None:
    if configured is None:
        monkeypatch.delenv("QT_QPA_PLATFORMTHEME", raising=False)
    else:
        monkeypatch.setenv("QT_QPA_PLATFORMTHEME", configured)
    monkeypatch.setattr(app_module, "setup_logging", MagicMock())

    app_module.main()

    assert os.environ["QT_QPA_PLATFORMTHEME"] == expected
