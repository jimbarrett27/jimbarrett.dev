"""Render a TRMNL panel locally, so layout can be checked without a push.

TRMNL renders the Liquid itself, so nothing here runs in production. It exists
because you get twelve webhook pushes an hour and designing a panel takes rather
more iterations than that.

Each panel module supplies its template and merge variables; this handles the
parts they share -- interpolating the Liquid, screenshotting at the device's
exact 800x480, and reducing that to 1-bit the way the firmware will. The 1-bit
version is the one to judge: a design can look fine in greyscale and fall apart
at one bit per pixel. The PNG steps need a Chrome on PATH; without one you still
get the HTML.
"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

PANEL_WIDTH = 800
PANEL_HEIGHT = 480
CHROME_BINARIES = ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser")

# The device is 1-bit, so anything neither black nor white is an artefact of
# antialiasing. A little is unavoidable on text; a lot means the design leans on
# greys that will not survive. Dithered photographs are exempt -- they are
# *meant* to be a cloud of black and white pixels.
GREY_FLOOR, GREY_CEILING = 40, 216
GREY_BUDGET = 0.05


def render_html(template_path: Path, merge_variables: dict) -> str:
    """Interpolate a panel template exactly as TRMNL would."""
    from liquid import Template  # dev-only dependency, imported lazily

    return Template(template_path.read_text()).render(**merge_variables)


def _screenshot(html_path: Path, png_path: Path) -> bool:
    chrome = next((c for c in CHROME_BINARIES if shutil.which(c)), None)
    if chrome is None:
        logger.warning("no Chrome on PATH (%s); skipping PNG", "/".join(CHROME_BINARIES))
        return False
    subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
         f"--screenshot={png_path}", f"--window-size={PANEL_WIDTH},{PANEL_HEIGHT}",
         "--default-background-color=FFFFFFFF", html_path.as_uri()],
        check=True, capture_output=True,
    )
    return True


def _to_one_bit(png_path: Path, out_path: Path) -> float:
    """Threshold to 1-bit and report the fraction of pixels that were mid-grey."""
    from PIL import Image

    grey = Image.open(png_path).convert("L")
    grey.convert("1", dither=Image.Dither.NONE).save(out_path)
    histogram = grey.histogram()
    return sum(histogram[GREY_FLOOR:GREY_CEILING]) / (grey.width * grey.height)


def preview(template_path: Path, merge_variables: dict, out_dir: Path,
            check_grey: bool = True) -> Path:
    """Write the HTML, PNG and 1-bit PNG for a panel. Returns the output directory.

    ``check_grey`` is for line-art panels; switch it off for a panel whose whole
    point is a dithered photograph, where a high mid-grey count is expected
    rather than a warning.
    """
    # Resolved because the screenshot step needs a file:// URI, which a relative
    # path cannot express.
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    html_path = out_dir / "panel.html"
    html_path.write_text('<!doctype html><meta charset="utf-8"><style>body{margin:0}</style>'
                         + render_html(template_path, merge_variables))
    logger.info("html  -> %s", html_path)

    png_path = out_dir / "panel.png"
    if _screenshot(html_path, png_path):
        logger.info("png   -> %s", png_path)
        one_bit_path = out_dir / "panel-1bit.png"
        grey_fraction = _to_one_bit(png_path, one_bit_path)
        logger.info("1-bit -> %s", one_bit_path)
        if check_grey:
            verdict = "ok" if grey_fraction <= GREY_BUDGET else "TOO MUCH GREY"
            logger.info("mid-grey %.1f%% (%s)", 100 * grey_fraction, verdict)
    return out_dir
