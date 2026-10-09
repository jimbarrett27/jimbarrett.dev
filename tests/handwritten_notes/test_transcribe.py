"""Tests for handwritten_notes.transcribe, with the vision call faked."""

import io

from PIL import Image

from handwritten_notes import transcribe


def _jpeg(size, orientation=None):
    out = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[transcribe.EXIF_ORIENTATION] = orientation
    Image.new("RGB", size, "white").save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_small_upright_image_passes_through_untouched():
    data = _jpeg((800, 600))
    assert transcribe.prepare(data, "image/png") == (data, "image/png")


def test_large_image_is_shrunk_to_the_max_edge():
    data, mime = transcribe.prepare(_jpeg((4000, 3000)), "image/jpeg")
    assert mime == "image/jpeg"
    assert max(Image.open(io.BytesIO(data)).size) == transcribe.MAX_EDGE_PX


def test_rotated_phone_photo_is_turned_upright():
    # Orientation 6: stored landscape, displayed portrait.
    data, _ = transcribe.prepare(_jpeg((1200, 900), orientation=6), "image/jpeg")
    assert Image.open(io.BytesIO(data)).size == (900, 1200)


def test_sends_all_pages_in_one_call_and_strips_fences(monkeypatch):
    calls = []

    def fake(template_path, params, images, model_name):
        calls.append((params, images, model_name))
        return "```markdown\n## Ideas\n- one\n```"

    monkeypatch.setattr(transcribe, "get_vision_response", fake)
    pages = [(_jpeg((100, 100)), "image/jpeg"), (_jpeg((100, 100)), "image/jpeg")]

    assert transcribe.transcribe(pages, caption="Ideas") == "## Ideas\n- one"
    [(params, images, model)] = calls
    assert params == {"pages": 2, "caption": "Ideas"}
    assert images == pages
    assert model == transcribe.MODEL
