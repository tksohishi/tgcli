from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tg_cli.auth import get_status, login, logout


class TestLogin:
    @patch("tg_cli.auth.save_session")
    @patch("tg_cli.auth.StringSession")
    @patch("tg_cli.auth.create_client")
    async def test_login_saves_session(self, mock_create, mock_ss, mock_save):
        client = AsyncMock()
        mock_create.return_value = client
        mock_ss.save.return_value = "saved_session"

        await login()

        client.start.assert_awaited_once()
        mock_save.assert_called_once_with("saved_session")
        client.disconnect.assert_awaited_once()


class TestLogout:
    @patch("tg_cli.auth.delete_session")
    @patch("tg_cli.auth.create_client")
    async def test_logout_authorized(self, mock_create, mock_delete):
        client = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=True)
        mock_create.return_value = client

        await logout()

        client.log_out.assert_awaited_once()
        mock_delete.assert_called_once()

    @patch("tg_cli.auth.delete_session")
    @patch("tg_cli.auth.create_client")
    async def test_logout_not_authorized(self, mock_create, mock_delete):
        client = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        mock_create.return_value = client

        await logout()

        client.log_out.assert_not_awaited()
        mock_delete.assert_called_once()

    @patch("tg_cli.auth.delete_session")
    @patch("tg_cli.auth.create_client")
    async def test_logout_deletes_session_when_client_fails(
        self, mock_create, mock_delete
    ):
        """Local session should be deleted even if remote logout fails."""
        mock_create.side_effect = RuntimeError("no config")

        await logout()

        mock_delete.assert_called_once()


class TestGetStatus:
    @patch("tg_cli.auth.create_client")
    @patch("tg_cli.auth.load_session", return_value=None)
    async def test_no_session(self, mock_load, mock_create):
        result = await get_status()

        assert result == {
            "authenticated": False,
            "phone": None,
            "session_exists": False,
        }
        mock_create.assert_not_called()

    @patch("tg_cli.auth.create_client")
    @patch("tg_cli.auth.load_session", return_value="some_session")
    async def test_authenticated_with_phone(self, mock_load, mock_create):
        client = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=True)
        client.get_me = AsyncMock(return_value=SimpleNamespace(phone="12345678901"))
        mock_create.return_value = client

        result = await get_status()

        assert result["authenticated"] is True
        assert result["session_exists"] is True
        assert result["phone"] == "123******01"

    @patch("tg_cli.auth.create_client")
    @patch("tg_cli.auth.load_session", return_value="some_session")
    async def test_session_exists_but_not_authorized(self, mock_load, mock_create):
        client = AsyncMock()
        client.is_user_authorized = AsyncMock(return_value=False)
        mock_create.return_value = client

        result = await get_status()

        assert result["authenticated"] is False
        assert result["session_exists"] is True
