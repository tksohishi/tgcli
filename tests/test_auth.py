from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from telethon.errors import PasswordHashInvalidError, SessionPasswordNeededError

from tgcli.auth import (
    QRLoginTimeout,
    _qr_ttl,
    get_status,
    login,
    login_qr,
    logout,
    migrate_session,
)


class TestLogin:
    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.StringSession")
    @patch("tgcli.auth.create_client")
    async def test_login_saves_session(self, mock_create, mock_ss, mock_save):
        client = AsyncMock()
        mock_create.return_value = client
        mock_ss.save.return_value = "saved_session"

        await login()

        client.start.assert_awaited_once()
        mock_save.assert_called_once_with("saved_session")
        client.disconnect.assert_awaited_once()


def _fake_qr(*, wait, ttl: float = 30.0, url: str = "tg://login?token=abc"):
    """A stand-in for Telethon's QRLogin. wait is the side_effect list."""
    qr = AsyncMock()
    qr.url = url
    qr.expires = datetime.now(tz=UTC) + timedelta(seconds=ttl)
    qr.wait = AsyncMock(side_effect=wait)
    return qr


def _fake_client(qr, *, authorized: bool = False, sign_in=None):
    client = AsyncMock()
    client.is_user_authorized = AsyncMock(return_value=authorized)
    client.qr_login = AsyncMock(return_value=qr)
    if sign_in is not None:
        client.sign_in = AsyncMock(side_effect=sign_in)
    return client


class TestQrTtl:
    def test_uses_the_tokens_own_expiry(self):
        qr = SimpleNamespace(expires=datetime.now(tz=UTC) + timedelta(seconds=25))

        assert 20 < _qr_ttl(qr, remaining=300.0) <= 25

    def test_remaining_budget_wins_when_smaller(self):
        qr = SimpleNamespace(expires=datetime.now(tz=UTC) + timedelta(seconds=90))

        assert _qr_ttl(qr, remaining=4.0) == 4.0

    def test_falls_back_to_the_cap_without_a_usable_expiry(self):
        assert _qr_ttl(SimpleNamespace(), remaining=300.0) == 120.0
        assert _qr_ttl(SimpleNamespace(expires="soon"), remaining=300.0) == 120.0

    def test_clamps_a_far_future_expiry_to_the_cap(self):
        qr = SimpleNamespace(expires=datetime.now(tz=UTC) + timedelta(days=1))

        assert _qr_ttl(qr, remaining=600.0) == 120.0

    def test_never_returns_a_non_positive_wait(self):
        qr = SimpleNamespace(expires=datetime.now(tz=UTC) - timedelta(seconds=60))

        assert _qr_ttl(qr, remaining=300.0) == 1.0
        assert _qr_ttl(qr, remaining=-5.0) == 1.0


class TestLoginQr:
    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.StringSession")
    @patch("tgcli.auth.create_client")
    async def test_saves_session_once_scanned(self, mock_create, mock_ss, mock_save):
        qr = _fake_qr(wait=[None])
        client = _fake_client(qr)
        mock_create.return_value = client
        mock_ss.save.return_value = "saved_session"
        shown = []

        await login_qr(on_token=lambda url, attempt: shown.append((url, attempt)))

        assert shown == [("tg://login?token=abc", 1)]
        mock_save.assert_called_once_with("saved_session")
        client.disconnect.assert_awaited_once()

    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.StringSession")
    @patch("tgcli.auth.create_client")
    async def test_rotates_the_token_when_it_expires(
        self, mock_create, mock_ss, mock_save
    ):
        """An expired token is the ordinary case: recreate and show it again."""
        qr = _fake_qr(wait=[TimeoutError(), TimeoutError(), None])
        mock_create.return_value = _fake_client(qr)
        mock_ss.save.return_value = "saved_session"
        shown = []

        await login_qr(on_token=lambda url, attempt: shown.append(attempt))

        assert shown == [1, 2, 3]
        assert qr.recreate.await_count == 2
        mock_save.assert_called_once_with("saved_session")

    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.StringSession")
    @patch("tgcli.auth.create_client")
    async def test_short_circuits_when_already_authorized(
        self, mock_create, mock_ss, mock_save
    ):
        qr = _fake_qr(wait=[None])
        client = _fake_client(qr, authorized=True)
        mock_create.return_value = client
        mock_ss.save.return_value = "saved_session"

        await login_qr(on_token=lambda url, attempt: None)

        client.qr_login.assert_not_awaited()
        mock_save.assert_called_once_with("saved_session")
        client.disconnect.assert_awaited_once()

    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.StringSession")
    @patch("tgcli.auth.create_client")
    async def test_signs_in_with_the_cloud_password_on_2fa(
        self, mock_create, mock_ss, mock_save
    ):
        """The scan is approved, then Telegram asks for the 2FA password."""
        qr = _fake_qr(wait=[SessionPasswordNeededError(request=None)])
        client = _fake_client(qr, sign_in=[None])
        mock_create.return_value = client
        mock_ss.save.return_value = "saved_session"

        answer = "hunter2"

        await login_qr(on_token=lambda url, attempt: None, password=lambda: answer)

        client.sign_in.assert_awaited_once_with(password=answer)
        mock_save.assert_called_once_with("saved_session")

    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.StringSession")
    @patch("tgcli.auth.create_client")
    async def test_retries_a_wrong_cloud_password(
        self, mock_create, mock_ss, mock_save
    ):
        qr = _fake_qr(wait=[SessionPasswordNeededError(request=None)])
        client = _fake_client(
            qr, sign_in=[PasswordHashInvalidError(request=None), None]
        )
        mock_create.return_value = client
        mock_ss.save.return_value = "saved_session"
        attempts = iter(["wrong", "right"])
        left = []

        await login_qr(
            on_token=lambda url, attempt: None,
            password=lambda: next(attempts),
            on_password_error=left.append,
        )

        assert left == [2]
        assert client.sign_in.await_count == 2
        mock_save.assert_called_once_with("saved_session")

    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.StringSession")
    @patch("tgcli.auth.create_client")
    async def test_gives_up_after_three_wrong_passwords(
        self, mock_create, mock_ss, mock_save
    ):
        qr = _fake_qr(wait=[SessionPasswordNeededError(request=None)])
        client = _fake_client(qr, sign_in=[PasswordHashInvalidError(request=None)] * 3)
        mock_create.return_value = client
        left = []

        with pytest.raises(PasswordHashInvalidError):
            await login_qr(
                on_token=lambda url, attempt: None,
                password=lambda: "wrong",
                on_password_error=left.append,
            )

        assert left == [2, 1]
        assert client.sign_in.await_count == 3
        mock_save.assert_not_called()
        client.disconnect.assert_awaited_once()

    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.create_client")
    async def test_reports_2fa_without_a_password_prompt(self, mock_create, mock_save):
        qr = _fake_qr(wait=[SessionPasswordNeededError(request=None)])
        mock_create.return_value = _fake_client(qr)

        with pytest.raises(ValueError, match="two-factor"):
            await login_qr(on_token=lambda url, attempt: None)

        mock_save.assert_not_called()

    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.create_client")
    async def test_raises_when_nobody_scans_before_the_deadline(
        self, mock_create, mock_save
    ):
        qr = _fake_qr(wait=[None])
        client = _fake_client(qr)
        mock_create.return_value = client

        with pytest.raises(QRLoginTimeout, match="within 0s"):
            await login_qr(on_token=lambda url, attempt: None, timeout=0)

        qr.wait.assert_not_awaited()
        mock_save.assert_not_called()
        client.disconnect.assert_awaited_once()

    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.create_client")
    async def test_disconnects_when_the_flow_blows_up(self, mock_create, mock_save):
        qr = _fake_qr(wait=[RuntimeError("boom")])
        client = _fake_client(qr)
        mock_create.return_value = client

        with pytest.raises(RuntimeError, match="boom"):
            await login_qr(on_token=lambda url, attempt: None)

        mock_save.assert_not_called()
        client.disconnect.assert_awaited_once()


class TestLogout:
    @patch("tgcli.auth.delete_session")
    @patch("tgcli.auth.create_client")
    async def test_logout_authorized(self, mock_create, mock_delete):
        client = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=True)
        mock_create.return_value = client

        await logout()

        client.log_out.assert_awaited_once()
        mock_delete.assert_called_once()

    @patch("tgcli.auth.delete_session")
    @patch("tgcli.auth.create_client")
    async def test_logout_not_authorized(self, mock_create, mock_delete):
        client = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        mock_create.return_value = client

        await logout()

        client.log_out.assert_not_awaited()
        mock_delete.assert_called_once()

    @patch("tgcli.auth.delete_session")
    @patch("tgcli.auth.create_client")
    async def test_logout_deletes_session_when_client_fails(
        self, mock_create, mock_delete
    ):
        """Local session should be deleted even if remote logout fails."""
        mock_create.side_effect = RuntimeError("no config")

        await logout()

        mock_delete.assert_called_once()


class TestMigrateSession:
    @patch("tgcli.auth.session_path")
    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.load_session")
    def test_migrates_keychain_session(self, mock_load, mock_save, mock_path):
        mock_load.return_value = "legacy_session"
        mock_path.return_value = "/tmp/session"

        result = migrate_session()

        mock_load.assert_called_once_with(store="keychain")
        mock_save.assert_called_once_with("legacy_session", store="file")
        assert result == {
            "migrated": True,
            "deleted_keychain": False,
            "path": "/tmp/session",
        }

    @patch("tgcli.auth.delete_session")
    @patch("tgcli.auth.session_path")
    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.load_session")
    def test_migrates_and_deletes_keychain(
        self, mock_load, mock_save, mock_path, mock_delete
    ):
        mock_load.return_value = "legacy_session"
        mock_path.return_value = "/tmp/session"

        result = migrate_session(delete_keychain=True)

        mock_save.assert_called_once_with("legacy_session", store="file")
        mock_delete.assert_called_once_with(store="keychain")
        assert result["deleted_keychain"] is True

    @patch("tgcli.auth.session_path")
    @patch("tgcli.auth.save_session")
    @patch("tgcli.auth.load_session")
    def test_missing_keychain_session(self, mock_load, mock_save, mock_path):
        mock_load.return_value = None
        mock_path.return_value = "/tmp/session"

        result = migrate_session()

        mock_save.assert_not_called()
        assert result == {
            "migrated": False,
            "deleted_keychain": False,
            "path": "/tmp/session",
        }


class TestGetStatus:
    @patch("tgcli.auth.create_client")
    @patch("tgcli.auth.load_session_store", return_value="file")
    @patch("tgcli.auth.load_session", return_value=None)
    async def test_no_session(self, mock_load, mock_store, mock_create):
        result = await get_status()

        assert result == {
            "authenticated": False,
            "phone": None,
            "session_exists": False,
            "session_store": "file",
        }
        mock_load.assert_called_once_with(store="file")
        mock_create.assert_not_called()

    @patch("tgcli.auth.create_client")
    @patch("tgcli.auth.load_session_store", return_value="file")
    @patch("tgcli.auth.load_session", return_value="some_session")
    async def test_authenticated_with_phone(self, mock_load, mock_store, mock_create):
        client = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=True)
        client.get_me = AsyncMock(return_value=SimpleNamespace(phone="12345678901"))
        mock_create.return_value = client

        result = await get_status()

        assert result["authenticated"] is True
        assert result["session_exists"] is True
        assert result["session_store"] == "file"
        assert result["phone"] == "123******01"

    @patch("tgcli.auth.create_client")
    @patch("tgcli.auth.load_session_store", return_value="keychain")
    @patch("tgcli.auth.load_session", return_value="some_session")
    async def test_session_exists_but_not_authorized(
        self, mock_load, mock_store, mock_create
    ):
        client = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        mock_create.return_value = client

        result = await get_status()

        assert result["authenticated"] is False
        assert result["session_exists"] is True
        assert result["session_store"] == "keychain"
        mock_load.assert_called_once_with(store="keychain")
