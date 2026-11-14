"""One-off OAuth consent for Drive: run once, sign in as the photos account.

    uv run python -m gcp_util.drive_auth [--client /home/jim/data/drive_oauth_client.json]

The server is headless, so the consent page opens in a browser on your laptop and
Google redirects back to ``localhost:<port>`` — forward that port first:

    ssh -L 8095:localhost:8095 <server>

Then open the printed URL on the laptop. The resulting refresh token is stored as a
new version of the ``DRIVE_OAUTH_TOKEN`` secret (created if missing), which is what
:mod:`gcp_util.drive` reads. Re-run it if the token is ever revoked.
"""

import argparse

from google.api_core.exceptions import AlreadyExists
from google.cloud import secretmanager
from google_auth_oauthlib.flow import InstalledAppFlow

from gcp_util.drive import PROJECT_ID, SCOPES, TOKEN_SECRET_ID, get_drive_service

DEFAULT_CLIENT_FILE = "/home/jim/data/drive_oauth_client.json"


def store_token(token_json: str) -> None:
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{PROJECT_ID}"
    try:
        client.create_secret(
            request={
                "parent": parent,
                "secret_id": TOKEN_SECRET_ID,
                "secret": {"replication": {"automatic": {}}},
            }
        )
    except AlreadyExists:
        pass
    client.add_secret_version(
        request={
            "parent": f"{parent}/secrets/{TOKEN_SECRET_ID}",
            "payload": {"data": token_json.encode("utf-8")},
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--client", default=DEFAULT_CLIENT_FILE, help="OAuth desktop client JSON")
    parser.add_argument("--port", type=int, default=8095)
    args = parser.parse_args()

    flow = InstalledAppFlow.from_client_secrets_file(args.client, SCOPES)
    # prompt=consent + offline access guarantees Google issues a refresh token,
    # even if this account has approved the app before.
    creds = flow.run_local_server(
        port=args.port,
        open_browser=False,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="Open this URL in a browser on your laptop:\n\n{url}\n",
        success_message="Done: Drive access granted. You can close this tab.",
    )
    if not creds.refresh_token:
        raise SystemExit("Google returned no refresh token; nothing stored.")

    store_token(creds.to_json())
    print(f"Stored refresh token in Secret Manager as {TOKEN_SECRET_ID}.")

    get_drive_service.cache_clear()
    about = get_drive_service().about().get(fields="user(emailAddress)").execute()
    print(f"Verified: Drive reachable as {about['user']['emailAddress']}.")


if __name__ == "__main__":
    main()
