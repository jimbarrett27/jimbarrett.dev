"""Google Drive access for the home server, as the photos account.

The tablet's Drive integration uses the same account, so a folder here is what the
reMarkable sees. Credentials are an OAuth refresh token (an "authorized user" JSON:
client id, client secret, refresh token) kept in Secret Manager as
``DRIVE_OAUTH_TOKEN``; :mod:`gcp_util.drive_auth` creates it. App passwords don't
work for the Drive API, hence OAuth.

The token carries the full ``drive`` scope so the server can read files it didn't
create (papers added by hand, exports written by the tablet), not just its own.
Callers keep to the folders they're meant for.
"""

import io
import json
import mimetypes
from functools import lru_cache
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from gcp_util.secrets import GCPSecret, get_gcp_secret

PROJECT_ID = "personal-website-318015"
TOKEN_SECRET_ID = "DRIVE_OAUTH_TOKEN"
SCOPES = ["https://www.googleapis.com/auth/drive"]

FOLDER_MIME = "application/vnd.google-apps.folder"
_FILE_FIELDS = "id, name, mimeType, modifiedTime, size, parents"


@lru_cache(maxsize=1)
def get_drive_service():
    """A Drive v3 client authorised as the photos account.

    google-auth refreshes the short-lived access token from the stored refresh
    token on demand, so one cached client is fine for a long-running process.
    """
    info = json.loads(
        get_gcp_secret(GCPSecret(project_id=PROJECT_ID, secret_id=TOKEN_SECRET_ID, version="latest"))
    )
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _quote(value: str) -> str:
    """Escape a string for use inside single quotes in a Drive ``q`` query."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _list(service, query: str) -> list[dict]:
    files: list[dict] = []
    page_token = None
    while True:
        response = (
            service.files()
            .list(
                q=query,
                fields=f"nextPageToken, files({_FILE_FIELDS})",
                pageToken=page_token,
                pageSize=100,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return files


def find_folder(name: str, parent_id: str = "root", service=None) -> Optional[str]:
    """ID of the folder called ``name`` directly under ``parent_id``, or None."""
    service = service or get_drive_service()
    query = (
        f"name = '{_quote(name)}' and mimeType = '{FOLDER_MIME}' "
        f"and '{_quote(parent_id)}' in parents and trashed = false"
    )
    matches = _list(service, query)
    return matches[0]["id"] if matches else None


def ensure_folder(path: str, service=None) -> str:
    """ID of the folder at ``path`` (e.g. ``"Papers/To read"``), creating any missing parts."""
    service = service or get_drive_service()
    parent_id = "root"
    for name in (part for part in path.split("/") if part):
        folder_id = find_folder(name, parent_id, service)
        if folder_id is None:
            folder_id = (
                service.files()
                .create(
                    body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent_id]},
                    fields="id",
                )
                .execute()["id"]
            )
        parent_id = folder_id
    return parent_id


def list_files(folder_id: str, service=None) -> list[dict]:
    """Files (not trashed) directly inside ``folder_id``, with id/name/mimeType/modifiedTime/size."""
    service = service or get_drive_service()
    return _list(service, f"'{_quote(folder_id)}' in parents and trashed = false")


def download_file(file_id: str, dest: Path, service=None) -> Path:
    """Download a (non-Google-Docs) file's bytes to ``dest``."""
    service = service or get_drive_service()
    dest.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, service.files().get_media(fileId=file_id))
    done = False
    while not done:
        _, done = downloader.next_chunk()
    dest.write_bytes(buffer.getvalue())
    return dest


def upload_file(
    path: Path, folder_id: str, name: Optional[str] = None, service=None
) -> str:
    """Upload ``path`` into ``folder_id`` and return the new file's ID."""
    service = service or get_drive_service()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    media = MediaFileUpload(str(path), mimetype=mime, resumable=True)
    created = (
        service.files()
        .create(
            body={"name": name or path.name, "parents": [folder_id]},
            media_body=media,
            fields="id",
        )
        .execute()
    )
    return created["id"]
