"""Tests for reMarkable notebooks arriving by email, with IMAP, Telegram and the model faked."""

from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from handwritten_notes import handwritten_bot, remarkable
from notes_routing import telegram as routing
from tests.handwritten_notes.test_handwritten_bot import FakeMessage

ME = 42
FOLDER = "Handwritten Notes"
GMAIL_PASS = ("mx.google.com; dkim=pass header.i=@share.remarkable.com; "
              "spf=pass smtp.mailfrom=bounce@share.remarkable.com; "
              "dmarc=pass (p=REJECT sp=REJECT dis=NONE) header.from=remarkable.com")


def _email(*, to="me+remarkable@gmail.com", sender="Jim <my@remarkable.com>",
           verdicts=(GMAIL_PASS,), subject="Document from my reMarkable: Standup",
           pages=(("Standup - page 2.png", b"p2"), ("Standup - page 1.png", b"p1"))) -> bytes:
    msg = EmailMessage()
    for verdict in verdicts:
        msg["Authentication-Results"] = verdict
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = "Thu, 12 Nov 2026 19:46:41 +0000"
    msg.set_content("Sent from my reMarkable paper tablet")
    for name, data in pages:
        msg.add_attachment(data, maintype="image", subtype="png", filename=name)
    return msg.as_bytes()


class FakeBot:
    def __init__(self):
        self.sent: list[FakeMessage] = []

    async def send_message(self, chat_id, text, **kwargs):
        assert chat_id == ME
        message = FakeMessage()
        message.text = text
        self.sent.append(message)
        return message


@pytest.fixture(autouse=True)
def fakes(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(tmp_path))
    monkeypatch.setenv("JIMBARRETT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(routing.router, "route", lambda *a: routing.router.Route(title=None))
    monkeypatch.setattr(remarkable, "get_telegram_user_id", lambda: ME)
    monkeypatch.setattr(remarkable, "_attempts", {})
    seen = []

    def fake_transcribe(pages, caption=None):
        seen.append((pages, caption))
        return "- [ ] Remember the milk"
    monkeypatch.setattr(handwritten_bot.transcribe, "transcribe", fake_transcribe)
    return SimpleNamespace(vault=tmp_path / FOLDER, seen=seen)


def test_parse_reads_title_time_and_pages_in_order():
    notebook = remarkable.parse(_email())
    assert notebook.title == "Standup"
    assert notebook.when.isoformat() == "2026-11-12T20:46:41+01:00"
    assert [(p.data, p.mime, p.ext) for p in notebook.pages] == [
        (b"p1", "image/png", "png"), (b"p2", "image/png", "png")]


@pytest.mark.parametrize("raw", [
    _email(to="me@gmail.com"),
    _email(sender="Someone <someone@example.com>"),
    _email(verdicts=(GMAIL_PASS.replace("dmarc=pass", "dmarc=fail"),)),
    _email(verdicts=()),
    # A forged pass below Gmail's own failing verdict doesn't count.
    _email(verdicts=(GMAIL_PASS.replace("dmarc=pass", "dmarc=fail"), GMAIL_PASS)),
], ids=["not-tagged", "wrong-sender", "dmarc-fail", "no-verdict", "forged-verdict"])
def test_untrusted_email_is_ignored(raw):
    assert remarkable.parse(raw) is None


@pytest.mark.asyncio
async def test_notebook_is_transcribed_and_filed(fakes):
    bot = FakeBot()
    assert await remarkable.handle(bot, "9", _email())

    [header] = bot.sent
    assert header.text == "📧 From the reMarkable: Standup (2 pages)"
    assert header.replies == ["- [ ] Remember the milk", f"📝 Saved to {FOLDER}/2026-11-12 2046.md"]
    assert fakes.seen == [([(b"p1", "image/png"), (b"p2", "image/png")], "Standup")]
    note = (fakes.vault / "2026-11-12 2046.md").read_text()
    assert "source: remarkable\n" in note and "# Standup\n" in note
    assert (fakes.vault / "images" / "2026-11-12 2046 p2.png").read_bytes() == b"p2"


@pytest.mark.asyncio
async def test_untrusted_email_is_dealt_with_silently(fakes):
    bot = FakeBot()
    assert await remarkable.handle(bot, "9", _email(sender="x@example.com"))
    assert bot.sent == [] and fakes.seen == []


@pytest.mark.asyncio
async def test_email_without_pngs_says_so(fakes):
    bot = FakeBot()
    assert await remarkable.handle(bot, "9", _email(pages=()))
    assert "without any PNG pages" in bot.sent[0].text
    assert fakes.seen == []


@pytest.mark.asyncio
async def test_failed_transcription_is_retried_then_given_up(monkeypatch, fakes):
    def broken(pages, caption=None):
        raise RuntimeError("model exploded")
    monkeypatch.setattr(handwritten_bot.transcribe, "transcribe", broken)

    bot = FakeBot()
    results = [await remarkable.handle(bot, "9", _email()) for _ in range(remarkable.MAX_ATTEMPTS)]
    assert results == [False] * (remarkable.MAX_ATTEMPTS - 1) + [True]
    assert bot.sent[0].replies[-1] == "I'll try again in 2 minutes."
    assert bot.sent[-1].replies[-1].startswith("Giving up")
    assert not fakes.vault.exists()


@pytest.mark.asyncio
async def test_poll_marks_only_handled_emails_read(monkeypatch, fakes):
    monkeypatch.setattr(remarkable, "fetch_unseen", lambda: [("1", _email()), ("2", _email())])
    outcomes = {"1": True, "2": False}

    async def fake_handle(bot, uid, raw):
        return outcomes[uid]
    monkeypatch.setattr(remarkable, "handle", fake_handle)
    marked = []
    monkeypatch.setattr(remarkable, "mark_seen", marked.append)

    await remarkable.poll(SimpleNamespace(bot=FakeBot()))
    assert marked == ["1"]


@pytest.mark.asyncio
async def test_poll_survives_the_inbox_being_down(monkeypatch, fakes):
    def down():
        raise OSError("no network")
    monkeypatch.setattr(remarkable, "fetch_unseen", down)
    await remarkable.poll(SimpleNamespace(bot=FakeBot()))  # logs, doesn't raise
