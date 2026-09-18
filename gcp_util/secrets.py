from google.cloud import secretmanager
from functools import lru_cache
from dataclasses import dataclass

@dataclass
class GCPSecret:
    """
    Simple dataclass to manage the details of a GCP secret
    """

    project_id: str
    secret_id: str
    version: str

    def get_name(self, client: secretmanager.SecretManagerServiceClient):
        """
        Return the name necessary for fetching the secret content
        """
        return client.secret_version_path(self.project_id, self.secret_id, self.version)


def get_gcp_secret(gcp_secret: GCPSecret) -> str:
    """
    Fetches and decodes the content of a GCP secret
    """

    client = secretmanager.SecretManagerServiceClient()

    # Get the secret.
    response = client.access_secret_version(
        request={"name": gcp_secret.get_name(client)}
    )

    return response.payload.data.decode("UTF-8")


def _bot_key(secret_id: str) -> str:
    return get_gcp_secret(GCPSecret(
        project_id="personal-website-318015", secret_id=secret_id, version="latest"
    ))


@lru_cache(maxsize=1)
def get_swedish_bot_key() -> str:
    return _bot_key("TELEGRAM_SWEDISH_BOT_KEY")


@lru_cache(maxsize=1)
def get_dnd_bot_key() -> str:
    return _bot_key("TELEGRAM_DND_BOT_KEY")


@lru_cache(maxsize=1)
def get_minecraft_bot_key() -> str:
    return _bot_key("TELEGRAM_MINECRAFT_BOT_KEY")


@lru_cache(maxsize=1)
def get_diary_bot_key() -> str:
    return _bot_key("TELEGRAM_DIARY_BOT_KEY")


@lru_cache(maxsize=1)
def get_memes_bot_key() -> str:
    return _bot_key("TELEGRAM_MEMES_BOT_KEY")


@lru_cache(maxsize=1)
def get_photos_bot_key() -> str:
    return _bot_key("TELEGRAM_PHOTOS_BOT_KEY")


@lru_cache(maxsize=1)
def get_zotero_api_key() -> str:
    """Zotero API key for the paper-triage Zotero pusher (build step 7)."""
    return _bot_key("ZOTERO_API_KEY")


@lru_cache(maxsize=1)
def get_zotero_user_id() -> str:
    """Personal Zotero library (user) ID for the paper-triage pusher."""
    return _bot_key("ZOTERO_USER_ID")


@lru_cache(maxsize=1)
def get_photo_email_address() -> str:
    return get_gcp_secret(GCPSecret(
        project_id="personal-website-318015", secret_id="JIMMY_PHOTO_EMAIL_ADDRESS", version="latest"
    ))


@lru_cache(maxsize=1)
def get_photo_email_password() -> str:
    return get_gcp_secret(GCPSecret(
        project_id="personal-website-318015", secret_id="JIMMY_PHOTO_EMAIL_PASSWORD", version="latest"
    )).replace(" ", "")


@lru_cache(maxsize=1)
def get_dnd_allowed_chat_ids() -> list[int]:
    try:
        raw = get_gcp_secret(GCPSecret(
            project_id="personal-website-318015", secret_id="DND_ALLOWED_CHAT_IDS", version="latest"
        ))
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    except Exception:
        return []


@lru_cache(maxsize=1)
def get_photos_allowed_user_ids() -> list[int]:
    raw = get_gcp_secret(GCPSecret(
        project_id="personal-website-318015", secret_id="PHOTOS_ALLOWED_USER_IDS", version="latest"
    ))
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


@lru_cache(maxsize=1)
def get_telegram_user_id() -> int:
    """
    Fetches the token for the main telegram bot
    """

    secret = GCPSecret(
        project_id="personal-website-318015", secret_id="TELEGRAM_USER_ID", version=1
    )

    return int(get_gcp_secret(secret))

@lru_cache(maxsize=1)
def get_telegram_secret_token() -> str:
    """
    Fetches the token for the main telegram bot
    """

    secret = GCPSecret(
        project_id="personal-website-318015", secret_id="TELEGRAM_BOT_RESPONSE_TOKEN", version=1
    )

    return get_gcp_secret(secret)


@lru_cache(maxsize=1)
def get_trmnl_meme_webhook_url() -> str:
    """Webhook for the daily-meme TRMNL private plugin.

    As with the fitness plugin, the UUID in the URL is the only credential TRMNL
    checks, so the whole URL is a secret rather than a config value.
    """
    return _bot_key("TRMNL_MEME_WEBHOOK_URL")


@lru_cache(maxsize=1)
def get_trmnl_fitness_webhook_url() -> str:
    """Webhook for the fitness TRMNL private plugin.

    The UUID in the URL is the only credential TRMNL checks, so treat the whole
    URL as a secret rather than a config value.
    """
    return _bot_key("TRMNL_FITNESS_WEBHOOK_URL")


@lru_cache(maxsize=1)
def get_intervals_api_key() -> str:
    """API key for intervals.icu (used as the *password*, with username ``API_KEY``)."""
    return _bot_key("INTERVALS_ICU_API_KEY")


@lru_cache(maxsize=1)
def get_openrouter_api_key() -> str:
    """Fetches the API key for OpenRouter."""
    secret = GCPSecret(
        project_id="personal-website-318015", secret_id="OPENROUTER_KEY", version=1
    )
    return get_gcp_secret(secret)
