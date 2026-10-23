from __future__ import annotations

from pathlib import Path

import pytest

from analytics.history.chronology_loader import ChronologyLoader
from analytics.history.chronology_renderer import ChronologyRenderer
from analytics.history.chronology_timeline import ChronologyTimeline
from analytics.history.exception import ChronologyFileError
from conf import CHRONOLOGY_DOC_PATH
from models.history.chronology import Chronology
from models.history.enums import EventKind
from scripts.docs.render_chronology import ChronologyDocWriter


@pytest.fixture(scope="module")
def shipped() -> Chronology:
    return ChronologyLoader().load()


class TestChronologyLoader:
    def test_the_shipped_chronology_is_complete(self, shipped: Chronology) -> None:
        assert len(shipped.segments) >= 15
        assert all(shipped.reigns_of(segment.key) for segment in shipped.segments), "every segment has a leader"
        assert {event.kind for event in shipped.events} == set(EventKind)
        assert all(reign.sources for reign in shipped.reigns)
        assert all(event.source and event.description for event in shipped.events)
        assert any(event.default for event in shipped.events)
        assert [reign.company for reign in shipped.reigns_of("browsers")] == ["netscape", "microsoft", "google"]

    @pytest.mark.parametrize("content", ["segments: [", "as_of: 2026\nreigns: [{segment: x, company: y, start: 1990}]"])
    def test_a_broken_chronology_is_reported(self, tmp_path: Path, content: str) -> None:
        broken = tmp_path / "chronology.yaml"
        broken.write_text(content, encoding="utf-8")

        with pytest.raises(ChronologyFileError):
            ChronologyLoader().load(broken)
        with pytest.raises(ChronologyFileError):
            ChronologyLoader().load(tmp_path / "missing.yaml")


class TestChronologyTimeline:
    def test_changes_of_leader_and_events_by_date(self, shipped: Chronology) -> None:
        timeline = ChronologyTimeline()

        entries = timeline.entries(shipped)

        assert [entry.when for entry in entries] == sorted(entry.when for entry in entries)
        leaderships = [entry for entry in entries if entry.kind == timeline.LEADERSHIP]
        assert len(leaderships) >= len(shipped.reigns)
        google = next(entry for entry in entries if entry.key == "reign:search:google:2002")
        assert google.what.startswith("Google takes the lead in web navigation & search, after Yahoo.")
        assert next(entry for entry in entries if entry.key == "event:cma-cloud").effect == "Pending"
        dec_end = [
            entry for entry in entries if entry.key.startswith("reign:minicomputers:dec") and entry.date == "1998"
        ]
        assert dec_end, "a lead ending without successor gets its own line"

    def test_names_and_periods(self, shipped: Chronology) -> None:
        timeline = ChronologyTimeline()
        ibm, lenovo = shipped.reigns_of("pcs")[1], shipped.reigns_of("pcs")[-1]

        assert timeline.name(EventKind.MARKET_ACCESS) == "Market access"
        assert timeline.period(ibm) == "1981\u20131994"
        assert timeline.period(lenovo) == "2013\u2013"


class TestChronologyRenderer:
    def test_the_committed_guide_is_up_to_date(self, shipped: Chronology) -> None:
        assert CHRONOLOGY_DOC_PATH.read_text(encoding="utf-8") == ChronologyRenderer().markdown(shipped), (
            "run `uv run render-chronology`"
        )

    def test_the_guide_prints_the_successions_and_every_event(self, shipped: Chronology) -> None:
        text = ChronologyRenderer().markdown(shipped)

        assert text.startswith(
            "[\u2191 Docs index](../README.md)\n\n# Leaders of digital infrastructure, 1964\u20132026"
        )
        assert "| PCs | Apple (1977\u20131981) \u2192 IBM (1981\u20131994) \u2192 Compaq" in text
        assert all(event.label.replace("|", "\\|") in text for event in shipped.events)
        assert "## What the chronology shows" in text
        assert text.endswith("\n")


class TestChronologyDocWriter:
    def test_write_then_check(self, tmp_path: Path) -> None:
        output = tmp_path / "guide.md"
        writer = ChronologyDocWriter()

        assert writer.parse(["--check", "--output", str(output)]) == 1
        assert writer.parse(["--output", str(output)]) == 0
        assert writer.parse(["--check", "--output", str(output)]) == 0
        assert output.read_text(encoding="utf-8") == writer.render()

    def test_a_broken_chronology_fails(self, tmp_path: Path) -> None:
        broken = tmp_path / "chronology.yaml"
        broken.write_text("segments: [", encoding="utf-8")

        assert ChronologyDocWriter().parse(["--source", str(broken), "--output", str(tmp_path / "out.md")]) == 1
