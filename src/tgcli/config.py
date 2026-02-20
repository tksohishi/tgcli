from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "tgcli" / "config.toml"


@dataclass(frozen=True)
class TelegramConfig:
    api_id: int
    api_hash: str


def _resolve_op(value: str) -> str:
    """Resolve 1Password references (op:// URIs) via the `op` CLI."""
    result = subprocess.run(  # noqa: S603
        ["op", "read", value],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _resolve_value(value: str | int) -> str:
    """Resolve a config value, handling op:// references."""
    s = str(value)
    if s.startswith("op://"):
        return _resolve_op(s)
    return s


def load_config(config_path: Path | None = None) -> TelegramConfig:
    """Load Telegram API credentials.

    Resolution order:
    1. Config TOML (resolve op:// refs via `op read`)
    2. Env vars TELEGRAM_API_ID, TELEGRAM_API_HASH
    3. Error with clear message
    """
    path = config_path or CONFIG_PATH
    api_id: str | None = None
    api_hash: str | None = None

    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        raw_id = data.get("api_id")
        raw_hash = data.get("api_hash")
        if raw_id is not None:
            api_id = _resolve_value(raw_id)
        if raw_hash is not None:
            api_hash = _resolve_value(raw_hash)

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

    return TelegramConfig(api_id=int(api_id), api_hash=api_hash)


def write_config(api_id: int, api_hash: str, config_path: Path | None = None) -> Path:
    """Write Telegram API credentials to a TOML config file.

    Creates parent directories if needed. Returns the path written to.
    """
    path = config_path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'api_id = {api_id}\napi_hash = "{api_hash}"\n')
    return path


def write_config_op(
    api_id: int,
    api_hash: str,
    vault: str = "Personal",
    item_title: str = "Telegram API",
    config_path: Path | None = None,
) -> Path:
    """Store credentials in 1Password and write op:// references to config."""
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "op",
            "item",
            "create",
            "--category",
            "login",
            "--title",
            item_title,
            "--vault",
            vault,
            f"api_id[text]={api_id}",
            f"api_hash[text]={api_hash}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    path = config_path or CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    op_id = f"op://{vault}/{item_title}/api_id"
    op_hash = f"op://{vault}/{item_title}/api_hash"
    path.write_text(f'api_id = "{op_id}"\napi_hash = "{op_hash}"\n')
    return path
