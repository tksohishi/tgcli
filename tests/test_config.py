from __future__ import annotations

import pytest

from tgcli.config import TelegramConfig, load_config, write_config


def test_load_from_toml(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('api_id = 123456\napi_hash = "abc123"\n')

    result = load_config(config_path=cfg)

    assert result == TelegramConfig(api_id=123456, api_hash="abc123")


def test_load_from_toml_string_api_id(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('api_id = "123456"\napi_hash = "abc123"\n')

    result = load_config(config_path=cfg)

    assert result == TelegramConfig(api_id=123456, api_hash="abc123")


def test_load_from_env(tmp_path, monkeypatch):
    """Falls back to env vars when TOML file doesn't exist."""
    cfg = tmp_path / "nonexistent.toml"
    monkeypatch.setenv("TELEGRAM_API_ID", "111")
    monkeypatch.setenv("TELEGRAM_API_HASH", "envhash")

    result = load_config(config_path=cfg)

    assert result == TelegramConfig(api_id=111, api_hash="envhash")


def test_env_fills_missing_toml_fields(tmp_path, monkeypatch):
    """Env vars fill in fields missing from TOML."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("api_id = 999\n")
    monkeypatch.setenv("TELEGRAM_API_HASH", "fromenv")

    result = load_config(config_path=cfg)

    assert result == TelegramConfig(api_id=999, api_hash="fromenv")


def test_missing_credentials_exits(tmp_path, monkeypatch):
    cfg = tmp_path / "nonexistent.toml"
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_API_HASH", raising=False)

    with pytest.raises(SystemExit, match="credentials not found"):
        load_config(config_path=cfg)


def test_write_config_creates_valid_toml(tmp_path):
    cfg = tmp_path / "sub" / "config.toml"

    write_config(123456, "abc123hash", config_path=cfg)

    assert cfg.exists()
    result = load_config(config_path=cfg)
    assert result == TelegramConfig(api_id=123456, api_hash="abc123hash")


def test_write_config_overwrites_existing(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('api_id = 1\napi_hash = "old"\n')

    write_config(999, "newhash", config_path=cfg)

    result = load_config(config_path=cfg)
    assert result == TelegramConfig(api_id=999, api_hash="newhash")
