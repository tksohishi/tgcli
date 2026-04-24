from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tgcli.auth import get_status, login, logout, migrate_session


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
