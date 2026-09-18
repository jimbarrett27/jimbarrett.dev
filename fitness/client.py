"""Read-only client for the intervals.icu API.

Authentication is HTTP Basic with the *literal* username ``API_KEY`` and the
personal API key as the password -- the key is not a bearer token::

    curl -u API_KEY:<key> https://intervals.icu/api/v1/athlete/i716993/wellness

Two gotchas worth keeping in this docstring, both found the hard way:

* The athlete id must carry its ``i`` prefix. ``i716993`` returns 200; the bare
  numeric ``716993`` returns 403, not 404, so it looks like an auth failure.
* ``/wellness`` silently clamps to roughly a year of history regardless of the
  ``oldest`` asked for, because that is as far back as the upstream Garmin sync
  has populated. Callers should treat a short series as normal, not an error.

Distances come back in metres and durations in seconds; conversion to display
units is :mod:`fitness.metrics`' job, not this module's.
"""

import logging
from datetime import date, timedelta

import requests

from gcp_util.secrets import get_intervals_api_key

logger = logging.getLogger(__name__)

BASE_URL = "https://intervals.icu/api/v1"
ATHLETE_ID = "i716993"
TIMEOUT_SECONDS = 60


def _auth() -> tuple[str, str]:
    return ("API_KEY", get_intervals_api_key())


def _get(path: str, params: dict | None = None) -> list | dict:
    """GET an athlete-scoped path, e.g. ``"wellness"``, and return parsed JSON."""
    url = f"{BASE_URL}/athlete/{ATHLETE_ID}/{path}"
    response = requests.get(url, params=params, auth=_auth(), timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def _window(days: int, today: date | None = None) -> dict[str, str]:
    end = today or date.today()
    return {
        "oldest": (end - timedelta(days=days)).isoformat(),
        "newest": end.isoformat(),
    }


def fetch_wellness(days: int = 90, today: date | None = None) -> list[dict]:
    """Daily wellness rows, oldest first.

    Each row carries ``id`` (the ISO date), ``ctl``, ``atl``, ``rampRate`` and,
    where the watch recorded them, ``restingHR``, ``hrv``, ``sleepSecs`` and
    ``steps``. ``weight`` is present in the schema but is effectively unused on
    this account, so nothing should depend on it.
    """
    rows = _get("wellness", _window(days, today))
    rows.sort(key=lambda row: row["id"])
    logger.info("fetched %d wellness days", len(rows))
    return rows


def fetch_activities(days: int = 28, today: date | None = None) -> list[dict]:
    """Completed activities in the window, oldest first.

    The response is wide (180+ fields); the ones that matter downstream are
    ``start_date_local``, ``type``, ``name``, ``icu_training_load``,
    ``moving_time`` (seconds) and ``distance`` (metres).
    """
    rows = _get("activities", _window(days, today))
    rows.sort(key=lambda row: row["start_date_local"])
    logger.info("fetched %d activities", len(rows))
    return rows
