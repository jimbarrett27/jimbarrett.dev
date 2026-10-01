"""Tests for fitness.daily -- the panel refresh job's alert-once behaviour."""

import asyncio
from unittest.mock import MagicMock

import pytest

from fitness import daily


@pytest.fixture
def context():
    ctx = MagicMock()
    ctx.bot_data = {"minecraft_bot": MagicMock()}
    return ctx


def _run(context, monkeypatch, outcomes):
    """Run the job once per outcome: True/False is TRMNL's answer, an exception raises."""
    for outcome in outcomes:
        def refresh(outcome=outcome):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        monkeypatch.setattr(daily, "refresh_panel", refresh)
        asyncio.run(daily.fitness_panel_task(context))
    return [c.args[0] for c in context.bot_data["minecraft_bot"].send_message_to_me.call_args_list]


def test_success_is_silent(context, monkeypatch):
    assert _run(context, monkeypatch, [True, True]) == []


def test_brief_outage_is_silent(context, monkeypatch):
    outcomes = [False] * (daily.ALERT_AFTER_FAILURES - 1) + [True]
    assert _run(context, monkeypatch, outcomes) == []


def test_sustained_outage_alerts_once_then_recovers(context, monkeypatch):
    outcomes = [RuntimeError("intervals.icu down")] * (daily.ALERT_AFTER_FAILURES + 3) + [True, True]
    messages = _run(context, monkeypatch, outcomes)
    assert len(messages) == 2
    assert "failed" in messages[0]
    assert "updating again" in messages[1]
