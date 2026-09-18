"""Public GCS hosting for the daily meme, so TRMNL's renderer can fetch it.

A TRMNL webhook carries 2KB of JSON, and a meme is a few hundred KB of pixels,
so the image cannot ride along with the data. Instead it is uploaded here and the
push sends only its URL, which the plugin's markup drops into an ``<img>``.
TRMNL fetches it server-side when it renders, which is why the object has to be
public-read rather than merely reachable by us.

Objects are named by date::

    memes/2026-09-18.png

That is deliberate: a stable URL would let TRMNL (or any cache between us and it)
serve yesterday's picture forever, and a new path each day sidesteps the question
entirely. It also means the name is guessable, which is fine for a meme built
from a public Hacker News headline and would not be for anything else.

The bucket is shared by every TRMNL plugin in this repo, not just memes -- hence
the name -- and is created by :mod:`memes.setup_bucket`.
"""

import logging
from datetime import date

from google.cloud import storage

logger = logging.getLogger(__name__)

PROJECT_ID = "personal-website-318015"
BUCKET_NAME = "personal-website-318015-trmnl"
MEME_BLOB = "memes/{day}.png"
PUBLIC_URL = "https://storage.googleapis.com/{bucket}/{blob}"


def upload_meme(image_bytes: bytes, day: date | None = None) -> str:
    """Upload today's meme and return the public URL TRMNL should fetch."""
    blob_name = MEME_BLOB.format(day=(day or date.today()).isoformat())
    bucket = storage.Client(project=PROJECT_ID).bucket(BUCKET_NAME)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(image_bytes, content_type="image/png")
    url = PUBLIC_URL.format(bucket=BUCKET_NAME, blob=blob_name)
    logger.info("uploaded meme (%d bytes) to %s", len(image_bytes), url)
    return url
