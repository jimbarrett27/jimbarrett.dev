"""Posting merge variables to a TRMNL private plugin's webhook.

Every TRMNL plugin in this repo pushes the same way -- a JSON body under
``merge_variables``, to a URL whose UUID is the only credential -- so the
transport lives here and each plugin supplies its own webhook and payload.

TRMNL renders the Liquid template itself, so what goes over the wire is data,
never an image. Anything genuinely pictorial has to be hosted somewhere their
renderer can fetch it and referenced by URL; see :mod:`memes.storage`.

The two limits worth naming rather than discovering from an opaque 4xx: payloads
above 2KB are rejected outright, and more than twelve pushes an hour returns 429.
"""

import json
import logging

import requests

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 2048  # 5120 on TRMNL+
TIMEOUT_SECONDS = 30


class PayloadTooLarge(ValueError):
    """Raised before sending, so the caller sees the size rather than a 4xx."""


def build_payload(merge_variables: dict) -> str:
    """Serialise into TRMNL's envelope, refusing anything over the size cap."""
    payload = json.dumps({"merge_variables": merge_variables}, separators=(",", ":"))
    size = len(payload.encode())
    if size > MAX_PAYLOAD_BYTES:
        raise PayloadTooLarge(
            f"{size} bytes exceeds TRMNL's {MAX_PAYLOAD_BYTES}: send less, or move "
            f"anything pictorial to a hosted URL"
        )
    logger.info("payload %d bytes of %d", size, MAX_PAYLOAD_BYTES)
    return payload


def push(webhook_url: str, merge_variables: dict) -> bool:
    """Send merge variables to a plugin webhook. Returns whether TRMNL accepted."""
    response = requests.post(
        webhook_url,
        data=build_payload(merge_variables),
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code == 429:
        logger.error("rate limited: TRMNL allows 12 pushes an hour on a standard plan")
        return False
    if not response.ok:
        logger.error("TRMNL rejected the push: HTTP %d %s",
                     response.status_code, response.text[:200])
        return False
    logger.info("pushed ok (HTTP %d)", response.status_code)
    return True
