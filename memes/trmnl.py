"""Push memes to the TRMNL e-ink display via its Image Webhook plugin.

TRMNL's image webhook is passthrough storage: whatever PNG we POST is what the
panel shows, with no server-side fitting or dithering. The panel is a 1-bit
800x480 e-ink screen, so we do that conversion ourselves — a meme handed over as
a full-colour JPEG comes out muddy, and text loses its edges.

The webhook URL *is* the credential (anyone holding it can write to the panel),
so it lives in Secret Manager alongside the bot tokens. ``TRMNL_MEME_WEBHOOK_URL``
in the environment overrides it, which is how you point a local run at a throwaway
plugin without touching the secret.
"""

import io
import logging
import os

import requests
from PIL import Image, ImageOps

from gcp_util.secrets import get_trmnl_meme_webhook_url

logger = logging.getLogger(__name__)

# TRMNL OG panel geometry.
PANEL_WIDTH = 800
PANEL_HEIGHT = 480

WEBHOOK_URL_ENV = "TRMNL_MEME_WEBHOOK_URL"

# The panel is far wider than a typical meme template, so images are letterboxed
# rather than cropped — a cropped meme usually loses half its punchline.
BACKGROUND = 255  # white, which is the e-ink panel's rest state


def prepare_for_panel(
    image_bytes: bytes,
    width: int = PANEL_WIDTH,
    height: int = PANEL_HEIGHT,
) -> bytes:
    """Fit an arbitrary meme into a 1-bit PNG the panel can render as-is.

    Greyscale -> autocontrast -> contain-fit onto a white canvas -> Floyd-Steinberg
    dither. Autocontrast matters more than it looks: e-ink has no midtones to
    spend, so stretching the range first keeps dithered photos from turning into
    uniform grey noise.
    """
    with Image.open(io.BytesIO(image_bytes)) as img:
        grey = ImageOps.autocontrast(img.convert("L"))

        scale = min(width / grey.width, height / grey.height)
        fitted = grey.resize(
            (max(1, round(grey.width * scale)), max(1, round(grey.height * scale))),
            Image.LANCZOS,
        )

        canvas = Image.new("L", (width, height), BACKGROUND)
        canvas.paste(
            fitted,
            ((width - fitted.width) // 2, (height - fitted.height) // 2),
        )

        buffer = io.BytesIO()
        # PIL's default convert("1") dither is Floyd-Steinberg.
        canvas.convert("1").save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


def _webhook_url() -> str:
    return os.environ.get(WEBHOOK_URL_ENV) or get_trmnl_meme_webhook_url()


def push_image(image_bytes: bytes, timeout: int = 30) -> None:
    """Prepare `image_bytes` for the panel and POST it to the image webhook.

    Raises on a failed upload; callers that treat the panel as a nice-to-have
    should catch. TRMNL allows 12 uploads an hour and rejects anything over 5MB,
    neither of which a once-daily 1-bit PNG comes close to.
    """
    panel_png = prepare_for_panel(image_bytes)
    response = requests.post(
        _webhook_url(),
        data=panel_png,
        headers={"Content-Type": "image/png"},
        timeout=timeout,
    )
    if not response.ok:
        # TRMNL explains itself in the body — a 422 is usually the webhook URL of
        # a *data* private plugin ("must be nested inside a merge_variables
        # payload"), which looks identical to an image one from the outside.
        raise requests.HTTPError(
            f"TRMNL rejected the image ({response.status_code}): {response.text[:500]}",
            response=response,
        )
    logger.info("Pushed %d bytes to the TRMNL panel", len(panel_png))


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="path to an image to send to the panel")
    parser.add_argument(
        "--preview",
        metavar="OUT.PNG",
        help="write the panel-ready PNG here instead of pushing it",
    )
    args = parser.parse_args()

    source = open(args.image, "rb").read()
    if args.preview:
        with open(args.preview, "wb") as handle:
            handle.write(prepare_for_panel(source))
        print(f"wrote {args.preview}", file=sys.stderr)
    else:
        push_image(source)
        print("pushed to TRMNL", file=sys.stderr)
