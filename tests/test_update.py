from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from tgcli.cli import app
from tgcli.update import (
    _fetch_latest_version,
    _load_state,
    _save_state,
    check_for_update,
    detect_install_method,
    format_update_notice,
)

runner = CliRunner()


class TestLoadState:
    def test_missing_file(self, tmp_path):
        assert _load_state(tmp_path / "missing.json") == {}

    def test_valid_json(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text('{"last_check": 100, "latest_version": "1.0.0"}')
        assert _load_state(path) == {"last_check": 100, "latest_version": "1.0.0"}

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "state.json"
        path.write_text("not json")
        assert _load_state(path) == {}


class TestSaveState:
    def test_creates_parents(self, tmp_path):
        path = tmp_path / "a" / "b" / "state.json"
        _save_state(path, {"last_check": 42})
        assert json.loads(path.read_text()) == {"last_check": 42}

    def test_overwrites(self, tmp_path):
        path = tmp_path / "state.json"
        _save_state(path, {"v": 1})
        _save_state(path, {"v": 2})
        assert json.loads(path.read_text()) == {"v": 2}


class TestFetchLatestVersion:
    @patch("tgcli.update.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        body = json.dumps({"info": {"version": "2.0.0"}}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert _fetch_latest_version() == "2.0.0"

    @patch("tgcli.update.urllib.request.urlopen", side_effect=OSError("timeout"))
    def test_network_error(self, mock_urlopen):
        assert _fetch_latest_version() is None


class TestCheckForUpdate:
    @patch("tgcli.update.get_current_version", return_value="1.0.0")
    @patch("tgcli.update._fetch_latest_version", return_value="2.0.0")
    def test_newer_version(self, mock_fetch, mock_ver, tmp_path):
        result = check_for_update(state_path=tmp_path / "state.json")
        assert result == "2.0.0"

    @patch("tgcli.update.get_current_version", return_value="2.0.0")
    @patch("tgcli.update._fetch_latest_version", return_value="2.0.0")
    def test_same_version(self, mock_fetch, mock_ver, tmp_path):
        result = check_for_update(state_path=tmp_path / "state.json")
        assert result is None

    @patch("tgcli.update.get_current_version", return_value="1.0.0")
    def test_within_cooldown_returns_cached(self, mock_ver, tmp_path):
        path = tmp_path / "state.json"
        _save_state(path, {"last_check": time.time(), "latest_version": "2.0.0"})

        with patch("tgcli.update._fetch_latest_version") as mock_fetch:
            result = check_for_update(state_path=path)
            mock_fetch.assert_not_called()

        assert result == "2.0.0"

    @patch("tgcli.update.get_current_version", return_value="2.0.0")
    def test_within_cooldown_same_version(self, mock_ver, tmp_path):
        path = tmp_path / "state.json"
        _save_state(path, {"last_check": time.time(), "latest_version": "2.0.0"})

        result = check_for_update(state_path=path)
        assert result is None

    @patch("tgcli.update.get_current_version", return_value="1.0.0")
    @patch("tgcli.update._fetch_latest_version", return_value=None)
    def test_fetch_failure(self, mock_fetch, mock_ver, tmp_path):
        result = check_for_update(state_path=tmp_path / "state.json")
        assert result is None


class TestDetectInstallMethod:
    @patch("shutil.which", return_value=None)
    def test_not_found(self, mock_which):
        assert detect_install_method() == "unknown"

    @patch("shutil.which", return_value="/opt/homebrew/bin/tg")
    def test_homebrew_apple_silicon(self, mock_which):
        assert detect_install_method() == "homebrew"

    @patch("shutil.which", return_value="/usr/local/bin/tg")
    @patch("pathlib.Path.resolve")
    def test_homebrew_intel_via_cellar(self, mock_resolve, mock_which):
        mock_resolve.return_value = Path("/usr/local/Cellar/tgcli/0.7.0/bin/tg")
        assert detect_install_method() == "homebrew"

    @patch("shutil.which", return_value="/home/user/.local/bin/tg")
    def test_uv(self, mock_which):
        assert detect_install_method() == "uv"

    @patch("shutil.which", return_value="/usr/bin/tg")
    @patch("pathlib.Path.resolve")
    def test_unknown(self, mock_resolve, mock_which):
        mock_resolve.return_value = Path("/usr/bin/tg")
        assert detect_install_method() == "unknown"


class TestFormatUpdateNotice:
    @patch("tgcli.update.detect_install_method", return_value="uv")
    @patch("tgcli.update.get_current_version", return_value="1.0.0")
    def test_uv_install(self, mock_ver, mock_method):
        msg = format_update_notice("2.0.0")
        assert "1.0.0" in msg
        assert "2.0.0" in msg
        assert "tg update" in msg

    @patch("tgcli.update.detect_install_method", return_value="homebrew")
    @patch("tgcli.update.get_current_version", return_value="1.0.0")
    def test_homebrew_install(self, mock_ver, mock_method):
        msg = format_update_notice("2.0.0")
        assert "brew upgrade tgcli" in msg
        assert "tg update" not in msg


class TestCLIUpdateCheck:
    @patch("tgcli.update.check_for_update", return_value="9.9.9")
    @patch(
        "tgcli.update.format_update_notice",
        return_value="Update available: 1.0.0 -> 9.9.9",
    )
    @patch("tgcli.update.detect_install_method", return_value="uv")
    @patch("subprocess.run")
    def test_notice_shows_in_output(
        self, mock_run, mock_method, mock_format, mock_check, monkeypatch
    ):
        monkeypatch.delenv("TGCLI_NO_UPDATE_CHECK", raising=False)
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch("tgcli.update.clear_update_state"):
            result = runner.invoke(app, ["update"])
        assert result.exit_code == 0
        assert "Update available" in result.output

    @patch("tgcli.update.check_for_update")
    @patch("tgcli.update.detect_install_method", return_value="uv")
    @patch("subprocess.run")
    def test_suppressed_by_env_var(self, mock_run, mock_method, mock_check):
        # TGCLI_NO_UPDATE_CHECK=1 set by conftest autouse fixture
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch("tgcli.update.clear_update_state"):
            result = runner.invoke(app, ["update"])
        assert result.exit_code == 0
        mock_check.assert_not_called()

    @patch("tgcli.update.detect_install_method", return_value="uv")
    @patch("subprocess.run")
    def test_update_command_success(self, mock_run, mock_method):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch("tgcli.update.clear_update_state"):
            result = runner.invoke(app, ["update"])

        assert result.exit_code == 0
        assert "upgraded successfully" in result.output

    @patch("tgcli.update.detect_install_method", return_value="uv")
    @patch("subprocess.run")
    def test_update_command_failure(self, mock_run, mock_method):
        mock_run.return_value = MagicMock(returncode=1, stderr="error details")

        result = runner.invoke(app, ["update"])

        assert result.exit_code == 1
        assert "Upgrade failed" in result.output

    @patch("tgcli.update.detect_install_method", return_value="homebrew")
    def test_update_command_homebrew(self, mock_method):
        result = runner.invoke(app, ["update"])

        assert result.exit_code == 0
        assert "brew upgrade tgcli" in result.output

    @patch("tgcli.update.detect_install_method", return_value="unknown")
    def test_update_command_unknown(self, mock_method):
        result = runner.invoke(app, ["update"])

        assert result.exit_code == 0
        assert "Upgrade manually" in result.output
