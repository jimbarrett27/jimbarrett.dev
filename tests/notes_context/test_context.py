"""Tests for notes_routing.context, and that every notes model gets to see it."""

import numpy as np
import pytest

from handwritten_notes import figures, transcribe
from notes_routing import context, router
from voice_notes import transcribe as whisper

NOTE = """---
tags: [meta]
---
I'm Jim. My girlfriend is Amanda. I write about work and D&D.

## Vocabulary
- Jim
- Amanda
* WHODrug
-

## Projects
- not a term
"""


@pytest.fixture(autouse=True)
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(root))
    return root


@pytest.fixture
def note(vault):
    (vault / context.CONTEXT_NOTE).write_text(NOTE)


def test_no_note_means_no_context():
    assert context.about() == ""
    assert context.vocabulary() == []


def test_about_is_the_note_without_frontmatter(note):
    assert context.about().startswith("I'm Jim.")
    assert "tags:" not in context.about()


def test_about_is_capped(vault):
    (vault / context.CONTEXT_NOTE).write_text("x" * 5000)
    assert len(context.about()) == context.MAX_CONTEXT_CHARS


def test_vocabulary_is_the_bullets_under_its_heading_only(note):
    assert context.vocabulary() == ["Jim", "Amanda", "WHODrug"]


def test_handwriting_prompt_gets_the_context(note, monkeypatch):
    seen = {}
    monkeypatch.setattr(transcribe, "get_vision_response",
                        lambda template, params, images, model_name: seen.update(params) or "ok")
    transcribe.transcribe([])
    assert seen["context"] == context.about()


def test_figure_prompts_get_the_context(note, monkeypatch):
    seen = []
    monkeypatch.setattr(figures, "prepare", lambda data, mime: (data, mime))
    monkeypatch.setattr(figures, "get_vision_response",
                        lambda template, params, images, model_name: seen.append(params) or "flowchart LR")
    figures.redraw_flowchart((b"", "image/jpeg"), "a loop")
    assert seen[0]["context"] == context.about()


def test_router_prompt_gets_the_context(note, monkeypatch):
    seen = {}
    monkeypatch.setattr(router, "get_llm_response",
                        lambda template, params: seen.update(params) or '{"title": "x"}')
    router.route("pancakes", None, "voice")
    assert seen["context"] == context.about()


@pytest.mark.parametrize("has_note, hotwords", [(True, "Jim, Amanda, WHODrug"), (False, None)])
def test_whisper_gets_the_vocabulary_as_hotwords(request, monkeypatch, has_note, hotwords):
    if has_note:
        request.getfixturevalue("note")
    seen = {}

    class FakeWhisper:
        def transcribe(self, samples, **options):
            seen.update(options)
            return [], None
    monkeypatch.setattr(whisper, "_model", lambda: FakeWhisper())
    whisper.transcribe(np.zeros(16000, dtype=np.float32))
    assert seen["hotwords"] == hotwords
