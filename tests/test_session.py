from __future__ import annotations

from unittest.mock import patch

import keyring.errors

from tgcli.session import delete_session, load_session, save_session


class TestSession:
    def test_save_session_file(self, tmp_path):
        session_path = tmp_path / "tgcli" / "session"

        save_session("abc123", store="file", session_path=session_path)

        assert session_path.read_text() == "abc123"
        assert session_path.stat().st_mode & 0o777 == 0o600
        assert session_path.parent.stat().st_mode & 0o777 == 0o700

    def test_load_session_file_exists(self, tmp_path):
        session_path = tmp_path / "session"
        session_path.write_text("stored_session\n")

        result = load_session(store="file", session_path=session_path)

        assert result == "stored_session"

    def test_load_session_file_missing(self, tmp_path):
        result = load_session(store="file", session_path=tmp_path / "missing")

        assert result is None

    def test_delete_session_file(self, tmp_path):
        session_path = tmp_path / "session"
        session_path.write_text("stored_session")

        delete_session(store="file", session_path=session_path)

        assert not session_path.exists()

    def test_delete_session_file_not_found(self, tmp_path):
        delete_session(store="file", session_path=tmp_path / "missing")

    @patch("tgcli.session.keyring")
    def test_save_session_keychain(self, mock_kr):
        save_session("abc123", store="keychain")

        mock_kr.set_password.assert_called_once_with(
            "tgcli", "telegram_session", "abc123"
        )

    @patch("tgcli.session.keyring")
    def test_load_session_keychain_exists(self, mock_kr):
        mock_kr.get_password.return_value = "stored_session"

        result = load_session(store="keychain")

        assert result == "stored_session"
        mock_kr.get_password.assert_called_once_with("tgcli", "telegram_session")

    @patch("tgcli.session.keyring")
    def test_load_session_keychain_missing(self, mock_kr):
        mock_kr.get_password.return_value = None

        result = load_session(store="keychain")

        assert result is None

    @patch("tgcli.session.keyring")
    def test_delete_session_keychain(self, mock_kr):
        delete_session(store="keychain")

        mock_kr.delete_password.assert_called_once_with("tgcli", "telegram_session")

    @patch("tgcli.session.keyring")
    def test_delete_session_keychain_not_found(self, mock_kr):
        mock_kr.delete_password.side_effect = keyring.errors.PasswordDeleteError()

        delete_session(store="keychain")
