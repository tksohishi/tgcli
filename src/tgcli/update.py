"""Update checking and self-update logic.

No Telethon, no CLI dependencies. Uses only stdlib.
"""

from __future__ import annotations

import json
import time
import urllib.request
from importlib.metadata import version
from pathlib import Path

_PYPI_URL = "https://pypi.org/pypi/pytgcli/json"
_COOLDOWN_SECONDS = 86400  # 24 hours
_TIMEOUT_SECONDS = 3
_DEFAULT_STATE_PATH = Path.home() / ".config" / "tgcli" / "update_check.json"


def get_current_version() -> str:
    return version("pytgcli")


def _load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _fetch_latest_version() -> str | None:
    """Fetch the latest version string from PyPI. Returns None on any failure."""
    try:
        req = urllib.request.Request(  # noqa: S310
            _PYPI_URL, headers={"Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:  # noqa: S310
            data = json.loads(resp.read())
        return data["info"]["version"]
    except Exception:  # noqa: BLE001
        return None


def _is_newer(latest: str, current: str) -> bool:
    """Compare version strings as tuples of ints."""

    def _parse(v: str) -> tuple[int, ...]:
        return tuple(int(x) for x in v.split("."))

    try:
        return _parse(latest) > _parse(current)
    except (ValueError, TypeError):
        return False


def check_for_update(state_path: Path | None = None) -> str | None:
    """Check PyPI for a newer version (at most once per 24h).

    Returns the latest version string if newer, else None. Never raises.
    """
    try:
        path = state_path or _DEFAULT_STATE_PATH
        state = _load_state(path)

        now = time.time()
        last_check = state.get("last_check", 0)

        if now - last_check < _COOLDOWN_SECONDS:
            cached = state.get("latest_version")
            if cached and _is_newer(cached, get_current_version()):
                return cached
            return None

        latest = _fetch_latest_version()
        if latest is None:
            return None

        _save_state(path, {"last_check": now, "latest_version": latest})

        if _is_newer(latest, get_current_version()):
            return latest
        return None
    except Exception:  # noqa: BLE001
        return None


def detect_install_method() -> str:
    """Detect how tgcli was installed. Returns 'homebrew', 'uv', or 'unknown'."""
    import shutil

    tg = shutil.which("tg")
    if tg is None:
        return "unknown"

    resolved = Path(tg).resolve()
    parts = resolved.parts
    if "Cellar" in parts or "homebrew" in parts:
        return "homebrew"
    if ".local" in parts:
        return "uv"
    return "unknown"


def clear_update_state(state_path: Path | None = None) -> None:
    """Remove cached update state (e.g. after a successful upgrade)."""
    path = state_path or _DEFAULT_STATE_PATH
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def format_update_notice(latest_version: str) -> str:
    current = get_current_version()
    method = detect_install_method()
    if method == "homebrew":
        hint = "Run `brew upgrade tgcli` to upgrade."
    else:
        hint = "Run `tg update` to upgrade."
    return f"Update available: {current} -> {latest_version}. {hint}"
