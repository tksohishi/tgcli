from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from telethon.errors import UnauthorizedError
from typer.testing import CliRunner

from tgcli.cli import app
from tgcli.formatting import MessageData

runner = CliRunner()


class TestAuthLogin:
    @patch("tgcli.auth.login", new_callable=AsyncMock)
    def test_login_success(self, mock_login):
        result = runner.invoke(app, ["auth", "login"])

        assert result.exit_code == 0
        assert "Login successful" in result.output

    @patch("tgcli.auth.login", new_callable=AsyncMock, side_effect=RuntimeError("fail"))
    def test_login_failure(self, mock_login):
        result = runner.invoke(app, ["auth", "login"])

        assert result.exit_code == 1


class TestAuthLogout:
    @patch("tgcli.auth.logout", new_callable=AsyncMock)
    def test_logout_success(self, mock_logout):
        result = runner.invoke(app, ["auth", "logout"])

        assert result.exit_code == 0
        assert "Logged out" in result.output


class TestAuthStatus:
    @patch("tgcli.auth.get_status", new_callable=AsyncMock)
    def test_status_authenticated(self, mock_status):
        mock_status.return_value = {
            "authenticated": True,
            "phone": "+1***99",
            "session_exists": True,
        }
        result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "authenticated" in result.output

    @patch("tgcli.auth.get_status", new_callable=AsyncMock)
    def test_status_not_authenticated(self, mock_status):
        mock_status.return_value = {
            "authenticated": False,
            "phone": None,
            "session_exists": False,
        }
        result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 0
        assert "not authenticated" in result.output

    @patch(
        "tgcli.auth.get_status",
        new_callable=AsyncMock,
        side_effect=SystemExit("credentials not found"),
    )
    def test_status_config_error_exits_1(self, mock_status):
        result = runner.invoke(app, ["auth", "status"])

        assert result.exit_code == 1
        assert "Configuration error" in result.output


class TestAuthSmart:
    """Tests for bare `tg auth` (no subcommand)."""

    @patch("tgcli.auth.get_status", new_callable=AsyncMock)
    @patch("tgcli.config.load_config")
    def test_auth_already_logged_in_shows_status(self, mock_load, mock_status):
        mock_load.return_value = MagicMock()
        mock_status.return_value = {
            "authenticated": True,
            "phone": "+1***99",
            "session_exists": True,
        }
        result = runner.invoke(app, ["auth"])

        assert result.exit_code == 0
        assert "authenticated" in result.output
        assert "tg auth logout" in result.output

    @patch("tgcli.auth.login", new_callable=AsyncMock)
    @patch("tgcli.auth.get_status", new_callable=AsyncMock)
    @patch("tgcli.config.load_config")
    def test_auth_not_logged_in_triggers_login(
        self, mock_load, mock_status, mock_login
    ):
        mock_load.return_value = MagicMock()
        mock_status.return_value = {
            "authenticated": False,
            "phone": None,
            "session_exists": False,
        }
        result = runner.invoke(app, ["auth"])

        assert result.exit_code == 0
        assert "Login successful" in result.output
        mock_login.assert_awaited_once()

    @patch("webbrowser.open")
    @patch("tgcli.auth.login", new_callable=AsyncMock)
    @patch("tgcli.auth.get_status", new_callable=AsyncMock)
    @patch("tgcli.config.write_config")
    @patch(
        "tgcli.config.load_config",
        side_effect=[SystemExit("credentials not found"), None],
    )
    def test_auth_no_config_prompts_and_creates(
        self, mock_load, mock_write, mock_status, mock_login, mock_wb_open
    ):
        mock_write.return_value = "/tmp/config.toml"
        mock_status.return_value = {
            "authenticated": False,
            "phone": None,
            "session_exists": False,
        }
        # Input: Enter to open browser, api_id, api_hash, decline 1Password
        result = runner.invoke(app, ["auth"], input="\n123456\nabc123\nn\n")

        assert result.exit_code == 0
        mock_write.assert_called_once_with(123456, "abc123")

    @patch("webbrowser.open")
    @patch("tgcli.auth.login", new_callable=AsyncMock)
    @patch("tgcli.auth.get_status", new_callable=AsyncMock)
    @patch("tgcli.config.write_config_op")
    @patch(
        "tgcli.config.load_config",
        side_effect=[SystemExit("credentials not found"), None],
    )
    def test_auth_no_config_stores_in_1password(
        self, mock_load, mock_write_op, mock_status, mock_login, mock_wb_open
    ):
        mock_write_op.return_value = "/tmp/config.toml"
        mock_status.return_value = {
            "authenticated": False,
            "phone": None,
            "session_exists": False,
        }
        # Input: Enter to open browser, api_id, api_hash, accept 1Password
        result = runner.invoke(app, ["auth"], input="\n123456\nabc123\ny\n")

        assert result.exit_code == 0
        mock_write_op.assert_called_once_with(123456, "abc123")

    @patch("webbrowser.open")
    @patch("tgcli.auth.login", new_callable=AsyncMock)
    @patch("tgcli.auth.get_status", new_callable=AsyncMock)
    @patch("tgcli.config.write_config")
    @patch(
        "tgcli.config.write_config_op", side_effect=FileNotFoundError("op not found")
    )
    @patch(
        "tgcli.config.load_config",
        side_effect=[SystemExit("credentials not found"), None],
    )
    def test_auth_1password_fails_falls_back_to_plain(
        self,
        mock_load,
        mock_write_op,
        mock_write,
        mock_status,
        mock_login,
        mock_wb_open,
    ):
        mock_write.return_value = "/tmp/config.toml"
        mock_status.return_value = {
            "authenticated": False,
            "phone": None,
            "session_exists": False,
        }
        # Input: open browser, api_id, api_hash, accept 1Password (fails)
        result = runner.invoke(app, ["auth"], input="\n123456\nabc123\ny\n")

        assert result.exit_code == 0
        assert "plain text" in result.output
        mock_write.assert_called_once_with(123456, "abc123")

    @patch("tgcli.config.load_config", side_effect=ValueError("invalid literal"))
    def test_auth_malformed_config_exits_1(self, mock_load):
        result = runner.invoke(app, ["auth"])

        assert result.exit_code == 1
        assert "Config error" in result.output


class TestSearch:
    @patch("tgcli.client.create_client")
    @patch("tgcli.client.search_messages", new_callable=AsyncMock)
    def test_search_pretty(self, mock_search, mock_create):
        client = AsyncMock()
        mock_create.return_value = client
        mock_search.return_value = [
            MessageData(
                id=1,
                text="hello world",
                chat_name="Group",
                sender_name="Bob",
                date=datetime(2025, 6, 15, 12, 0, tzinfo=UTC),
            ),
        ]
        result = runner.invoke(app, ["search", "hello", "--pretty"])

        assert result.exit_code == 0
        assert "hello world" in result.output

    @patch("tgcli.client.create_client")
    @patch("tgcli.client.search_messages", new_callable=AsyncMock)
    def test_search_jsonl_default(self, mock_search, mock_create):
        client = AsyncMock()
        mock_create.return_value = client
        mock_search.return_value = [
            MessageData(
                id=1,
                text="hello world",
                chat_name="Group",
                sender_name="Bob",
                date=datetime(2025, 6, 15, 12, 0, tzinfo=UTC),
            ),
            MessageData(
                id=2,
                text="second",
                chat_name="DM",
                sender_name="Eve",
                date=datetime(2025, 6, 15, 13, 0, tzinfo=UTC),
            ),
        ]
        result = runner.invoke(app, ["search", "hello"])

        assert result.exit_code == 0
        lines = result.output.strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["text"] == "hello world"
        assert first["chat_name"] == "Group"
        second = json.loads(lines[1])
        assert second["text"] == "second"

    @patch("tgcli.client.create_client")
    @patch("tgcli.client.search_messages", new_callable=AsyncMock)
    def test_search_no_results(self, mock_search, mock_create):
        client = AsyncMock()
        mock_create.return_value = client
        mock_search.return_value = []

        result = runner.invoke(app, ["search", "nothing"])

        assert result.exit_code == 0
        assert "No messages found" in result.output

    def test_search_invalid_after_date(self):
        result = runner.invoke(app, ["search", "hello", "--after", "2025-99-99"])

        assert result.exit_code == 1
        assert "Invalid date format" in result.output

    def test_search_invalid_before_date(self):
        result = runner.invoke(app, ["search", "hello", "--before", "not-a-date"])

        assert result.exit_code == 1
        assert "Invalid date format" in result.output

    @patch("tgcli.client.create_client")
    @patch("tgcli.client.search_messages", new_callable=AsyncMock)
    def test_search_unauthorized_exits_2(self, mock_search, mock_create):
        client = AsyncMock()
        mock_create.return_value = client
        mock_search.side_effect = UnauthorizedError(None, None)

        result = runner.invoke(app, ["search", "hello"])

        assert result.exit_code == 2
        assert "Not authenticated" in result.output

    @patch(
        "tgcli.client.create_client", side_effect=SystemExit("credentials not found")
    )
    def test_search_config_error_exits_1(self, mock_create):
        result = runner.invoke(app, ["search", "hello"])

        assert result.exit_code == 1
        assert "Configuration error" in result.output


class TestThread:
    @patch("tgcli.client.create_client")
    @patch("tgcli.client.get_thread_context", new_callable=AsyncMock)
    def test_thread_pretty(self, mock_thread, mock_create):
        client = AsyncMock()
        mock_create.return_value = client
        mock_thread.return_value = (
            [
                MessageData(
                    id=10,
                    text="target msg",
                    chat_name="Group",
                    sender_name="Alice",
                    date=datetime(2025, 6, 15, 12, 0, tzinfo=UTC),
                ),
            ],
            10,
            None,
        )
        result = runner.invoke(app, ["thread", "Group", "10", "--pretty"])

        assert result.exit_code == 0
        assert "target msg" in result.output

    @patch("tgcli.client.create_client")
    @patch("tgcli.client.get_thread_context", new_callable=AsyncMock)
    def test_thread_jsonl_default(self, mock_thread, mock_create):
        client = AsyncMock()
        mock_create.return_value = client
        replied = MessageData(
            id=9,
            text="original",
            chat_name="Group",
            sender_name="Bob",
            date=datetime(2025, 6, 15, 11, 0, tzinfo=UTC),
        )
        mock_thread.return_value = (
            [
                MessageData(
                    id=9,
                    text="original",
                    chat_name="Group",
                    sender_name="Bob",
                    date=datetime(2025, 6, 15, 11, 0, tzinfo=UTC),
                ),
                MessageData(
                    id=10,
                    text="target msg",
                    chat_name="Group",
                    sender_name="Alice",
                    date=datetime(2025, 6, 15, 12, 0, tzinfo=UTC),
                    reply_to_msg_id=9,
                ),
            ],
            10,
            replied,
        )
        result = runner.invoke(app, ["thread", "Group", "10"])

        assert result.exit_code == 0
        lines = result.output.strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["text"] == "original"
        assert first.get("replied_to") is True
        assert "target" not in first
        second = json.loads(lines[1])
        assert second["text"] == "target msg"
        assert second.get("target") is True
        assert "replied_to" not in second

    @patch("tgcli.client.create_client")
    @patch("tgcli.client.get_thread_context", new_callable=AsyncMock)
    def test_thread_unauthorized_exits_2(self, mock_thread, mock_create):
        client = AsyncMock()
        mock_create.return_value = client
        mock_thread.side_effect = UnauthorizedError(None, None)

        result = runner.invoke(app, ["thread", "Group", "10"])

        assert result.exit_code == 2
        assert "Not authenticated" in result.output

    @patch(
        "tgcli.client.create_client", side_effect=SystemExit("credentials not found")
    )
    def test_thread_config_error_exits_1(self, mock_create):
        result = runner.invoke(app, ["thread", "Group", "10"])

        assert result.exit_code == 1
        assert "Configuration error" in result.output


class TestHelp:
    def test_main_help(self):
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "search" in result.output.lower()
        assert "thread" in result.output.lower()
        assert "auth" in result.output.lower()

    def test_auth_help(self):
        result = runner.invoke(app, ["auth", "--help"])

        assert result.exit_code == 0
        assert "login" in result.output.lower()
        assert "logout" in result.output.lower()
        assert "status" in result.output.lower()
