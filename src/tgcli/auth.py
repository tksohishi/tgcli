from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime

from telethon.errors import PasswordHashInvalidError, SessionPasswordNeededError
from telethon.sessions import StringSession

from tgcli.client import create_client
from tgcli.config import load_session_store
from tgcli.session import delete_session, load_session, save_session, session_path

# Total time a QR login may spend waiting to be scanned, across however
# many token rotations fit inside it.
QR_LOGIN_TIMEOUT = 300.0
# Cap on one wait() round. A token's own TTL is normally well under this;
# the cap only guards a server that hands out a far-future expiry.
_QR_MAX_WAIT = 120.0
_MAX_PASSWORD_ATTEMPTS = 3


class QRLoginTimeout(Exception):
    """Nobody scanned the QR code before the overall deadline.

    Distinct from the `TimeoutError` that `QRLogin.wait` raises for a
    single expired token -- which is the ordinary case, and only means it
    is time to rotate the code.
    """


async def login() -> None:
    """Interactive login: phone + code/2FA. Saves the local session."""
    client = create_client()
    try:
        await client.start(phone=lambda: input("Phone number: "))
        session_str = StringSession.save(client.session)
        save_session(session_str)
    finally:
        await client.disconnect()


def _qr_ttl(qr, *, remaining: float) -> float:
    """Seconds to wait on one token: its own TTL, clamped.

    recreate() hands back the *same* token while it is still valid, so a
    round has to wait out the real expiry for the rotation to produce a
    fresh code.
    """
    expires = getattr(qr, "expires", None)
    if isinstance(expires, datetime):
        ttl = (expires - datetime.now(tz=UTC)).total_seconds()
    else:
        ttl = _QR_MAX_WAIT
    return max(1.0, min(ttl, _QR_MAX_WAIT, remaining))


async def _sign_in_2fa(
    client,
    password: Callable[[], str] | None,
    on_password_error: Callable[[int], None] | None,
) -> None:
    """Finish a scan that Telegram approved but which wants the cloud password."""
    if password is None:
        raise ValueError(
            "This account has two-factor authentication enabled, "
            "but no password prompt is available."
        )
    for attempts_left in range(_MAX_PASSWORD_ATTEMPTS - 1, -1, -1):
        try:
            await client.sign_in(password=password())
            return
        except PasswordHashInvalidError:
            if not attempts_left:
                raise
            if on_password_error:
                on_password_error(attempts_left)


async def login_qr(
    *,
    on_token: Callable[[str, int], None],
    password: Callable[[], str] | None = None,
    on_password_error: Callable[[int], None] | None = None,
    timeout: float = QR_LOGIN_TIMEOUT,
) -> None:
    """Authorize by QR code and save the local session.

    A device that is already logged in scans the code and approves this
    session, so nothing has to be delivered to a phone number -- the path
    that works when Telegram silently drops login codes for an IP.

    on_token(url, attempt) is called with each ``tg://login`` token, once
    per rotation, for the caller to display. Accounts with 2FA call
    password() for the cloud password, and on_password_error(attempts_left)
    after a wrong one.
    """
    client = create_client()
    try:
        await client.connect()
        if await client.is_user_authorized():
            save_session(StringSession.save(client.session))
            return

        qr = await client.qr_login()
        deadline = time.monotonic() + timeout
        attempt = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QRLoginTimeout(
                    f"No device scanned the QR code within {timeout:.0f}s."
                )
            attempt += 1
            on_token(qr.url, attempt)
            try:
                await qr.wait(timeout=_qr_ttl(qr, remaining=remaining))
            except TimeoutError:
                await qr.recreate()  # token expired: rotate, same login
                continue
            except SessionPasswordNeededError:
                await _sign_in_2fa(client, password, on_password_error)
            break

        save_session(StringSession.save(client.session))
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
