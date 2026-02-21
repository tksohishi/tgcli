from __future__ import annotations

import keyring
from keyring.errors import PasswordDeleteError

SERVICE_NAME = "tg-cli"
SESSION_KEY = "telegram_session"


def save_session(session_string: str) -> None:
    """Store the Telethon StringSession in the system keychain."""
    keyring.set_password(SERVICE_NAME, SESSION_KEY, session_string)


def load_session() -> str | None:
    """Load the Telethon StringSession from the system keychain.

    Returns None if no session is stored.
    """
    return keyring.get_password(SERVICE_NAME, SESSION_KEY)


def delete_session() -> None:
    """Remove the stored session from the system keychain."""
    try:
        keyring.delete_password(SERVICE_NAME, SESSION_KEY)
    except PasswordDeleteError:
        pass
