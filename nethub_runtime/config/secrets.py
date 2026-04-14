from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    api_key: str | None = None
    api_token: str | None = None

    mail_address: str | None = None
    mail_server: str | None = None
    mail_port: int | None = None
    mail_user: str | None = None
    mail_password: str | None = None
    mail_use_tls: bool = True
    mail_use_ssl: bool = False


_settings: Settings | None = None


def _maybe_load_dotenv() -> None:
    """If python-dotenv is installed and a .env file exists, load it.

    This is optional; absence of python-dotenv is fine.
    """
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    env_path = os.path.join(os.path.abspath(os.curdir), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _maybe_load_dotenv()
        s = Settings()
        s.api_key = os.getenv("API_KEY") or None
        s.api_token = os.getenv("API_TOKEN") or None

        s.mail_address = os.getenv("MAIL_ADDRESS") or None
        s.mail_server = os.getenv("MAIL_SERVER") or None
        mail_port = os.getenv("MAIL_PORT")
        s.mail_port = int(mail_port) if mail_port and mail_port.isdigit() else None
        s.mail_user = os.getenv("MAIL_USER") or None
        s.mail_password = os.getenv("MAIL_PASSWORD") or None
        s.mail_use_tls = _parse_bool(os.getenv("MAIL_USE_TLS"), True)
        s.mail_use_ssl = _parse_bool(os.getenv("MAIL_USE_SSL"), False)

        _settings = s
    return _settings


def as_dict() -> dict[str, Any]:
    return asdict(get_settings())
