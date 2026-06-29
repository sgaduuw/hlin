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

    # Flask session signing key. Required in production for login sessions
    # to survive a restart; if unset, a per-process ephemeral key is used
    # (fine for dev, logs everyone out on restart).
    secret_key: str | None = None

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
