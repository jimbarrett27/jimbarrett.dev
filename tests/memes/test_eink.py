"""Unit tests for preparing a meme for the 1-bit panel (no network, no LLM)."""

import io

import pytest
from PIL import Image

from memes.eink import (
    SIDE_BOX,
    STACK_BOX,
    PreparedMeme,
    choose_layout,
    prepare,
)


def meme_bytes(width: int, height: int, mode: str = "RGB") -> bytes:
    """A gradient, so there is real tonal range to dither."""
    img = Image.new(mode, (width, height))
    img.putdata([( (x * 255) // max(width - 1, 1),) * 3
                 for _ in range(height) for x in range(width)])
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


@pytest.mark.parametrize(
    "width,height,expected",
    [
        (889, 500, "stack"),   # always_has_been
        (750, 500, "stack"),   # distracted_boyfriend
        (700, 449, "stack"),   # grus_plan
        (578, 433, "stack"),   # change_my_mind
        (500, 500, "side"),    # drake
        (400, 600, "side"),    # taller than wide
    ],
)
def test_layout_follows_aspect_ratio(width, height, expected):
    layout, _ = choose_layout(width, height)
    assert layout == expected


def test_every_template_shape_stays_large_enough_to_read():
    """A meme's caption is burned in, so heavy downscaling makes it unreadable.

    The side-by-side layout scaled wide memes to ~56%, which is what drove the
    adaptive layout; nothing should regress below 80%.
    """
    for width, height in [(889, 500), (578, 433), (750, 500), (500, 500), (698, 500)]:
        _, box = choose_layout(width, height)
        scale = min(box[0] / width, box[1] / height)
        assert scale >= 0.80, f"{width}x{height} scaled to {scale:.0%}"


def test_prepare_fits_the_box_and_reports_its_size():
    result = prepare(meme_bytes(889, 500))
    assert isinstance(result, PreparedMeme)
    assert result.layout == "stack"
    assert result.width <= STACK_BOX[0] and result.height <= STACK_BOX[1]

    img = Image.open(io.BytesIO(result.png))
    assert (img.width, img.height) == (result.width, result.height)


def test_square_memes_use_the_side_box():
    result = prepare(meme_bytes(500, 500))
    assert result.layout == "side"
    assert result.width <= SIDE_BOX[0] and result.height <= SIDE_BOX[1]


def test_output_is_eight_bit_but_only_black_and_white():
    """TRMNL rejects bit-depth-1 PNGs, so the dither is stored at 8 bits."""
    img = Image.open(io.BytesIO(prepare(meme_bytes(800, 450)).png))
    assert img.mode == "L"
    assert {value for _, value in img.getcolors(maxcolors=256)} == {0, 255}


def test_small_memes_are_not_upscaled():
    result = prepare(meme_bytes(300, 200))
    assert (result.width, result.height) == (300, 200)
