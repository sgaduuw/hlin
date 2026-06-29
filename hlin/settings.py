"""Env-driven configuration.

12-factor: every knob that varies between deploys reads from the
environment at startup via this one pydantic-settings class. Callers read
``settings.foo`` rather than touching ``os.environ`` themselves. Prefix is
``HLIN_`` (e.g. ``HLIN_DB_PATH``, ``HLIN_HORIZON_DAYS``).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HLIN_", env_file=".env", extra="ignore")

    # On-disk SQLite path. Documented as the single backup target for an
    # external Restic job (see README).
    db_path: str = "hlin.db"

    # Recall horizon: obligations whose derived next-due falls within this
    # many days show on the dashboard "Coming up / Overdue" panel.
    horizon_days: int = 60

    # Flask session signing key. If unset, a key is generated once and
    # persisted beside the database so it stays stable across gunicorn
    # workers and restarts (see create_app). Set it explicitly to share a
    # key across hosts or to keep it out of the data volume.
    secret_key: str | None = None

    # Mark the session cookie Secure (browser only returns it over HTTPS).
    # Default off so plain-HTTP dev works; set true in production, where TLS
    # terminates at the reverse proxy in front of the app.
    session_cookie_secure: bool = False

    # If set, reads also require login (full lockdown). Off by default:
    # reads are open and only sensitive fields are redacted for anonymous.
    require_login: bool = False

    # Optional single outbound reminder channel.
    ntfy_url: str | None = None
    ntfy_topic: str | None = None

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


settings = Settings()
