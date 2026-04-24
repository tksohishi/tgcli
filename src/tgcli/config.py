from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

CONFIG_DIR = Path.home() / ".config" / "tgcli"
CONFIG_PATH = CONFIG_DIR / "config.toml"
SessionStore = Literal["file", "keychain"]


@dataclass(frozen=True)
class TelegramConfig:
    api_id: int
    api_hash: str
    session_store: SessionStore = "file"


def _parse_session_store(value: object) -> SessionStore:
    store = str(value or "file").lower()
    if store not in {"file", "keychain"}:
        raise ValueError('session_store must be "file" or "keychain"')
    return cast(SessionStore, store)


def load_session_store(config_path: Path | None = None) -> SessionStore:
    """Load the configured session backend without requiring API credentials."""
    path = config_path or CONFIG_PATH
    raw_store: object = None

    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        raw_store = data.get("session_store")

    return _parse_session_store(os.environ.get("TGCLI_SESSION_STORE", raw_store))


def load_config(config_path: Path | None = None) -> TelegramConfig:
    """Load Telegram API credentials.

    Resolution order:
    1. Config TOML
    2. Env vars TELEGRAM_API_ID, TELEGRAM_API_HASH
    3. Error with clear message
    """
    path = config_path or CONFIG_PATH
    api_id: str | None = None
    api_hash: str | None = None
    session_store: SessionStore = "file"

    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        raw_id = data.get("api_id")
        raw_hash = data.get("api_hash")
        if raw_id is not None:
            api_id = str(raw_id)
        if raw_hash is not None:
            api_hash = str(raw_hash)

    session_store = load_session_store(path)

    if api_id is None:
        api_id = os.environ.get("TELEGRAM_API_ID")
    if api_hash is None:
        api_hash = os.environ.get("TELEGRAM_API_HASH")

    if not api_id or not api_hash:
        raise SystemExit(
            "Telegram API credentials not found.\n"
            f"Set them in {CONFIG_PATH} or via "
            "TELEGRAM_API_ID / TELEGRAM_API_HASH env vars."
        )

    return TelegramConfig(
        api_id=int(api_id), api_hash=api_hash, session_store=session_store
    )


def write_config(api_id: int, api_hash: str, config_path: Path | None = None) -> Path:
    """Write Telegram API credentials to a TOML config file.

    Creates parent directories if needed. Returns the path written to.
    """
    path = config_path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'api_id = {api_id}\napi_hash = "{api_hash}"\nsession_store = "file"\n'
    )
    return path
