from __future__ import annotations

import pytest

from crawler import main


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    main()

    assert capsys.readouterr().out == "Hello from poc-crawler!\n"
