"""Tests for routing kept papers to the reMarkable, and paywalled stubs."""

from pathlib import Path

from triage import obsidian, routing
from triage.config import Settings

from tests.triage.test_obsidian import make_paper

DRIVE_ON = dict(drive_enabled=True)


def test_sent_paper_records_file_id(monkeypatch):
    monkeypatch.setattr(routing.outbound, "send_to_tablet", lambda p: "drive-1")
    paper = make_paper()
    routing.route_decision(paper, Settings(**DRIVE_ON))
    assert paper.drive_file_id == "drive-1"
    assert not paper.pdf_unavailable and paper.drive_error is None


def test_failure_is_recorded_and_retried(monkeypatch):
    def broken(paper):
        raise ConnectionError("Drive down")
    monkeypatch.setattr(routing.outbound, "send_to_tablet", broken)
    paper = make_paper()
    settings = Settings(**DRIVE_ON)
    routing.route_and_schedule(paper, settings)
    assert paper.drive_error == "Drive down"
    assert not routing.is_routing_complete(paper, settings)
    assert paper.next_retry_at is not None


def test_no_pdf_completes_drive_routing(monkeypatch):
    monkeypatch.setattr(routing.outbound, "send_to_tablet", lambda p: None)
    paper = make_paper()
    settings = Settings(**DRIVE_ON)
    routing.route_decision(paper, settings)
    assert paper.pdf_unavailable and paper.drive_file_id is None
    assert routing.is_routing_complete(paper, settings)


def test_idempotent_once_sent(monkeypatch):
    calls = []
    monkeypatch.setattr(routing.outbound, "send_to_tablet", lambda p: calls.append(p) or "x")
    routing.route_decision(make_paper(drive_file_id="done"), Settings(**DRIVE_ON))
    routing.route_decision(make_paper(pdf_unavailable=True), Settings(**DRIVE_ON))
    assert calls == []


def test_disabled_or_not_kept_does_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(routing.outbound, "send_to_tablet", lambda p: calls.append(p) or "x")
    routing.route_decision(make_paper(), Settings(drive_enabled=False))
    routing.route_decision(make_paper(status="deep"), Settings(**DRIVE_ON))
    routing.route_decision(make_paper(status="dismissed"), Settings(**DRIVE_ON))
    assert calls == []
    assert routing.is_routing_complete(make_paper(), Settings(drive_enabled=False))


def test_paywalled_stub_written_to_paywalled(monkeypatch, tmp_path):
    monkeypatch.setattr(routing.outbound, "send_to_tablet", lambda p: None)
    paper = make_paper(id=31)
    routing.route_decision(paper, Settings(drive_enabled=True, obsidian_vault=str(tmp_path),
                                           obsidian_inbox_subdir="Papers"))
    assert paper.obsidian_path.startswith("Papers/paywalled/")
    text = (tmp_path / paper.obsidian_path).read_text()
    assert "No open-access PDF" in text and "`31 - <title>.pdf`" in text


def test_stub_written_earlier_moves_to_paywalled(monkeypatch, tmp_path):
    settings = Settings(drive_enabled=True, obsidian_vault=str(tmp_path),
                        obsidian_inbox_subdir="Papers")

    def broken(paper):
        raise ConnectionError("Drive down")
    monkeypatch.setattr(routing.outbound, "send_to_tablet", broken)
    paper = make_paper()
    routing.route_decision(paper, settings)
    assert paper.obsidian_path.startswith("Papers/unread/")

    monkeypatch.setattr(routing.outbound, "send_to_tablet", lambda p: None)
    routing.route_decision(paper, settings)
    assert paper.obsidian_path.startswith("Papers/paywalled/")
    assert (tmp_path / paper.obsidian_path).exists()
    assert not list((tmp_path / "Papers" / "unread").iterdir())


def test_move_to_paywalled_leaves_a_stub_you_already_moved(tmp_path):
    assert obsidian.move_to_paywalled(tmp_path, "Papers/unread/gone.md", "Papers") \
        == "Papers/unread/gone.md"
    assert not (tmp_path / "Papers" / "paywalled").exists()
