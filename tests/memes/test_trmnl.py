"""Tests for the TRMNL panel push."""

import io

import pytest
from PIL import Image

from memes import trmnl


def _png(width: int, height: int, colour=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "size",
    [(1200, 1200), (500, 300), (2000, 400), (40, 900)],
)
def test_prepare_produces_a_1bit_panel_sized_png(size):
    with Image.open(io.BytesIO(trmnl.prepare_for_panel(_png(*size)))) as out:
        assert out.size == (trmnl.PANEL_WIDTH, trmnl.PANEL_HEIGHT)
        assert out.mode == "1"


def test_prepare_letterboxes_rather_than_crops():
    """A tall meme keeps its full height, padded left and right with white."""
    prepared = trmnl.prepare_for_panel(_png(480, 960, colour=(0, 0, 0)))
    with Image.open(io.BytesIO(prepared)) as out:
        pixels = out.convert("L")
        # Black content is centred and reaches the top and bottom edges...
        assert pixels.getpixel((trmnl.PANEL_WIDTH // 2, 0)) == 0
        assert pixels.getpixel((trmnl.PANEL_WIDTH // 2, trmnl.PANEL_HEIGHT - 1)) == 0
        # ...while the sides are the white rest state.
        assert pixels.getpixel((0, trmnl.PANEL_HEIGHT // 2)) == 255


def test_push_posts_the_prepared_png_to_the_webhook(monkeypatch):
    monkeypatch.setenv(trmnl.WEBHOOK_URL_ENV, "https://example.invalid/hook")
    calls = {}

    class _Response:
        ok = True
        status_code = 200

    def fake_post(url, data, headers, timeout):
        calls.update(url=url, data=data, headers=headers, timeout=timeout)
        return _Response()

    monkeypatch.setattr(trmnl.requests, "post", fake_post)
    trmnl.push_image(_png(600, 400))

    assert calls["url"] == "https://example.invalid/hook"
    assert calls["headers"] == {"Content-Type": "image/png"}
    with Image.open(io.BytesIO(calls["data"])) as sent:
        assert sent.size == (trmnl.PANEL_WIDTH, trmnl.PANEL_HEIGHT)
        assert sent.mode == "1"


def test_push_surfaces_trmnls_rejection_message(monkeypatch):
    """A data-webhook URL 422s; the body is the only thing that explains why."""
    monkeypatch.setenv(trmnl.WEBHOOK_URL_ENV, "https://example.invalid/hook")

    class _Response:
        ok = False
        status_code = 422
        text = '{"message":"Must be nested inside a merge_variables payload object"}'

    monkeypatch.setattr(
        trmnl.requests, "post", lambda url, data, headers, timeout: _Response()
    )

    with pytest.raises(trmnl.requests.HTTPError, match="merge_variables"):
        trmnl.push_image(_png(600, 400))


def test_env_var_overrides_the_secret(monkeypatch):
    def explode():
        raise AssertionError("Secret Manager should not be consulted")

    monkeypatch.setattr(trmnl, "get_trmnl_meme_webhook_url", explode)
    monkeypatch.setenv(trmnl.WEBHOOK_URL_ENV, "https://example.invalid/override")
    assert trmnl._webhook_url() == "https://example.invalid/override"
