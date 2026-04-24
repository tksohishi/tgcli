from __future__ import annotations

from telethon.sessions import StringSession

from tgcli.client import create_client
from tgcli.config import load_session_store
from tgcli.session import delete_session, load_session, save_session, session_path


async def login() -> None:
    """Interactive login: phone + code/2FA. Saves the local session."""
    client = create_client()
    try:
        await client.start(phone=lambda: input("Phone number: "))
        session_str = StringSession.save(client.session)
        save_session(session_str)
    finally:
        await client.disconnect()


async def logout() -> None:
    """Log out and remove the local session.

    Always deletes the local session, even if the remote logout fails.
    """
    try:
        client = create_client()
        try:
            await client.connect()
            if await client.is_user_authorized():
                await client.log_out()
        finally:
            await client.disconnect()
    except Exception:  # noqa: S110
        pass
    delete_session()


def migrate_session(*, delete_keychain: bool = False) -> dict[str, object]:
    """Copy the legacy keychain session to the file backend."""
    legacy_session = load_session(store="keychain")
    if not legacy_session:
        return {
            "migrated": False,
            "deleted_keychain": False,
            "path": session_path(),
        }

    save_session(legacy_session, store="file")
    deleted_keychain = False
    if delete_keychain:
        delete_session(store="keychain")
        deleted_keychain = True

    return {
        "migrated": True,
        "deleted_keychain": deleted_keychain,
        "path": session_path(),
    }


async def get_status() -> dict:
    """Return auth status info.

    Returns dict with keys: authenticated, phone, session_exists.
    """
    session_store = load_session_store()
    session_exists = load_session(store=session_store) is not None

    if not session_exists:
        return {
            "authenticated": False,
            "phone": None,
            "session_exists": False,
            "session_store": session_store,
        }

    client = create_client()
    try:
        await client.connect()
        authorized = await client.is_user_authorized()
        phone = None
        if authorized:
            me = await client.get_me()
            if me and me.phone:
                # Mask phone: show first 3 and last 2 digits
                p = me.phone
                if len(p) > 5:
                    phone = p[:3] + "*" * (len(p) - 5) + p[-2:]
                else:
                    phone = p
    finally:
        await client.disconnect()

    return {
        "authenticated": authorized,
        "phone": phone,
        "session_exists": session_exists,
        "session_store": session_store,
    }
