from __future__ import annotations

from pathlib import Path

import keyring
from keyring.errors import PasswordDeleteError

from tgcli.config import CONFIG_DIR, SessionStore, load_session_store

SERVICE_NAME = "tgcli"
SESSION_KEY = "telegram_session"
SESSION_PATH = CONFIG_DIR / "session"


def _resolve_store(store: SessionStore | None) -> SessionStore:
    return store or load_session_store()


def save_session(
    session_string: str,
    *,
    store: SessionStore | None = None,
    session_path: Path = SESSION_PATH,
) -> None:
    """Store the Telethon StringSession using the configured backend."""
    if _resolve_store(store) == "keychain":
        keyring.set_password(SERVICE_NAME, SESSION_KEY, session_string)
        return

    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.parent.chmod(0o700)
    session_path.write_text(session_string)
    session_path.chmod(0o600)


def load_session(
    *,
    store: SessionStore | None = None,
    session_path: Path = SESSION_PATH,
) -> str | None:
    """Load the Telethon StringSession from the configured backend.

    Returns None if no session is stored.
    """
    if _resolve_store(store) == "keychain":
        return keyring.get_password(SERVICE_NAME, SESSION_KEY)

    if not session_path.exists():
        return None
    session = session_path.read_text().strip()
    return session or None


def delete_session(
    *,
    store: SessionStore | None = None,
    session_path: Path = SESSION_PATH,
) -> None:
    """Remove the stored session from the configured backend."""
    if _resolve_store(store) == "file":
        try:
            session_path.unlink()
        except FileNotFoundError:
            pass
        return

    try:
        keyring.delete_password(SERVICE_NAME, SESSION_KEY)
    except PasswordDeleteError:
        pass


def session_path() -> Path:
    """Return the default file-backed session path."""
    return SESSION_PATH
