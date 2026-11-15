"""Tests for the one-off triage_id backfill of Obsidian stubs."""

from pathlib import Path
from types import SimpleNamespace

import yaml

from triage.backfill_stub_ids import add_triage_id, plan_backfill

OLD_STUB = """---
title: 'EDEN: A Large-Scale Corpus of Clinical Notes for Italian, with a title long
  enough to wrap'
authors:
- Tiziano Labruna
url: https://arxiv.org/abs/2606.12569v1
status: unread
tags:
- paper
---

# EDEN

## Notes

Hand-written notes --- with dashes.
"""


def _paper(id, url="https://x", title="Some paper", obsidian_path=None):
    return SimpleNamespace(id=id, url=url, title=title, obsidian_path=obsidian_path)


def _stub(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_add_triage_id_goes_after_a_wrapped_title_and_keeps_the_rest():
    out = add_triage_id(OLD_STUB, 7)
    fm = yaml.safe_load(out.split("---")[1])
    assert fm["triage_id"] == 7
    assert list(fm)[:3] == ["title", "triage_id", "authors"]
    assert fm["title"].endswith("long enough to wrap")
    assert out.replace("triage_id: 7\n", "") == OLD_STUB


def test_add_triage_id_without_frontmatter():
    assert add_triage_id("# Just a note\n", 7) is None


def test_plan_matches_by_path_then_url_then_title(tmp_path):
    vault = tmp_path
    root = vault / "Papers"
    by_path = _stub(root, "read/a.md", "---\ntitle: A\nurl: https://moved\n---\n")
    by_url = _stub(root, "unread/b.md", "---\ntitle: Whatever\nurl: https://b\n---\n")
    by_title = _stub(root, "paywalled/c.md", "---\ntitle: 'The C Paper!'\nurl: https://old\n---\n")
    done = _stub(root, "read/d.md", "---\ntitle: D\ntriage_id: 4\n---\n")
    nothing = _stub(root, "unread/e.md", "---\ntitle: Unknown\nurl: https://nope\n---\n")
    ambiguous = _stub(root, "unread/f.md", "---\ntitle: Dup\nurl: https://dup\n---\n")
    _stub(root, "unread/g.md", "no frontmatter\n")

    papers = [
        _paper(1, url="https://a", title="A", obsidian_path="Papers/read/a.md"),
        _paper(2, url="https://b", title="B"),
        _paper(3, url="https://c", title="the c paper"),
        _paper(5, url="https://dup", title="Dup one"),
        _paper(6, url="https://dup", title="Dup two"),
    ]
    plans = {p.path: (p.paper_id, p.reason) for p in plan_backfill(root, vault, papers)}

    assert plans[by_path] == (1, "matched by recorded path")
    assert plans[by_url] == (2, "matched by URL")
    assert plans[by_title] == (3, "matched by title")
    assert plans[done] == (None, "skipped: already has triage_id")
    assert plans[nothing] == (None, "skipped: no matching paper")
    assert plans[ambiguous] == (None, "skipped: URL matches papers [5, 6]")
    assert plans[root / "unread/g.md"] == (None, "skipped: no frontmatter")
