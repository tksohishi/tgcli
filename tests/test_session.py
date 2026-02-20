from __future__ import annotations

from unittest.mock import patch

import keyring.errors

from tgcli.session import delete_session, load_session, save_session


@patch("tgcli.session.keyring")
class TestSession:
    def test_save_session(self, mock_kr):
        save_session("abc123")

        mock_kr.set_password.assert_called_once_with(
            "tgcli", "telegram_session", "abc123"
        )

    def test_load_session_exists(self, mock_kr):
        mock_kr.get_password.return_value = "stored_session"

        result = load_session()

        assert result == "stored_session"
        mock_kr.get_password.assert_called_once_with("tgcli", "telegram_session")

    def test_load_session_missing(self, mock_kr):
        mock_kr.get_password.return_value = None

        result = load_session()

        assert result is None

    def test_delete_session(self, mock_kr):
        delete_session()

        mock_kr.delete_password.assert_called_once_with("tgcli", "telegram_session")

    def test_delete_session_not_found(self, mock_kr):
        mock_kr.delete_password.side_effect = keyring.errors.PasswordDeleteError()

        # Should not raise
        delete_session()
