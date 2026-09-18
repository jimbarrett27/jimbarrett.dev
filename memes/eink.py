"""Prepare a meme for a 1-bit e-ink panel.

A meme is a photograph with text burned into it, and photographs are the hardest
thing to put on a 1-bit display: every tone that is neither black nor white has
to be faked with dithering. Doing that conversion here rather than leaving it to
the device means the result is previewable -- what :func:`prepare` writes is
exactly what the panel shows.

Two adjustments earn their place, both established by looking at the output:

* **Tonal stretch and a midtone lift.** Dithering loses shadow detail first, so a
  source that is merely a bit dark collapses into a solid black mass. Stretching
  the histogram and lifting midtones first keeps faces and edges legible.
* **Floyd-Steinberg rather than a threshold.** A plain threshold is right for the
  line art of the fitness panel and wrong here; on a photograph it throws away
  every gradient. Error diffusion keeps the picture recognisable.

The meme is sized for the image half of the panel, not the whole screen -- the
headline occupies the rest, rendered as real text by TRMNL rather than dithered
into the picture, which keeps it crisp.
"""

import io
import logging
from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger(__name__)

# Two layouts, because the templates are not one shape. A meme carries its own
# burned-in caption, so how far the picture is scaled down decides whether that
# caption can be read -- which makes the fit the whole ballgame.
#
# Most templates are wide (889x500, 750x500, 700x449...); only drake is square.
# Squeezing a wide meme into a side column alongside a headline scales it to
# about 56% and its caption becomes unreadable, so wide memes instead fill the
# panel with the headline as a one-line footer (about 84%). Square memes have
# width to spare and keep the side-by-side column.
SIDE_BOX = (500, 430)   # square-ish meme, headline in a column beside it
STACK_BOX = (790, 418)  # wide meme, headline on a single footer line
STACK_ABOVE_ASPECT = 1.25

AUTOCONTRAST_CUTOFF = 2  # percent clipped from each end of the histogram
BRIGHTNESS_LIFT = 1.18


@dataclass
class PreparedMeme:
    """A dithered meme, the size it must be drawn at, and the layout that suits it.

    The size matters: the markup has to state it explicitly, because letting the
    browser scale a dithered image resamples the dither pattern into grey mush.
    """

    png: bytes
    width: int
    height: int
    layout: str  # "stack" (wide, headline below) or "side" (square, beside)


def choose_layout(width: int, height: int) -> tuple[str, tuple[int, int]]:
    """Pick the layout that leaves this meme's own caption largest."""
    if width / height >= STACK_ABOVE_ASPECT:
        return "stack", STACK_BOX
    return "side", SIDE_BOX


def prepare(image_bytes: bytes) -> PreparedMeme:
    """Scale, tone-correct and dither a meme to 1-bit for the panel."""
    source = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    layout, box = choose_layout(source.width, source.height)

    scale = min(box[0] / source.width, box[1] / source.height)
    if scale < 1:
        source = source.resize(
            (round(source.width * scale), round(source.height * scale)), Image.LANCZOS
        )

    grey = ImageOps.autocontrast(source.convert("L"), cutoff=AUTOCONTRAST_CUTOFF)
    grey = ImageEnhance.Brightness(grey).enhance(BRIGHTNESS_LIFT)
    dithered = grey.convert("1", dither=Image.Dither.FLOYDSTEINBERG)

    # Saved as 8-bit greyscale, not as a 1-bit PNG. The pixels are identical --
    # still only black and white, still the same dither -- but TRMNL's image
    # decoder rejects bit-depth-1 PNGs with "Unsupported image format" even
    # though it lists PNG as supported. Costs some file size, buys acceptance.
    out = io.BytesIO()
    dithered.convert("L").save(out, format="PNG", optimize=True)
    logger.info(
        "prepared meme for e-ink: %dx%d (%s layout, %.0f%% of original), %d bytes",
        dithered.width, dithered.height, layout, 100 * scale, out.tell(),
    )
    return PreparedMeme(out.getvalue(), dithered.width, dithered.height, layout)
