# AGENTS.md

This file provides guidance to AI coding agents working with code in this repository.

## Overview

A CLI tool (`tg`) to search and read Telegram messages from the terminal. Wraps Telegram's API for personal message access.

## Tech Stack

Python 3.12+, uv, Typer, Telethon, keyring.

## Architecture

```
src/tgcli/
  __init__.py
  cli.py          # Typer app, thin entrypoints
  auth.py         # Login/logout/status logic
  client.py       # Telethon wrapper (search, thread)
  config.py       # Config loading (TOML + env vars + op://)
  formatting.py   # Pure output formatting functions (no I/O)
  session.py      # Keychain-backed StringSession via keyring
tests/
  ...             # pytest + pytest-asyncio, Telethon fully mocked
```

Layers: CLI (Typer) -> business logic (auth, client) -> Telethon. Keep Telethon isolated from CLI and formatting layers. Formatting is pure functions, easy to test independently.

## Auth

Config lives at `~/.config/tgcli/config.toml`:

```toml
api_id = "op://Personal/Telegram API/api_id"
api_hash = "op://Personal/Telegram API/api_hash"
```

Plain values also work. Resolution order:
1. Config TOML (resolve `op://` refs via `op read`)
2. Env vars `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`
3. Error with clear message

Session auth key stored in macOS Keychain via `keyring` + Telethon's `StringSession`.

## Commands

- `tg auth login` - Interactive login (phone + code/2FA), saves session to Keychain
- `tg auth logout` - Remove session from Keychain
- `tg auth status` - Show auth state, masked phone, session existence
- `tg search <query>` - Search messages across chats; flags: `--chat`, `--from`, `--limit`, `--after`, `--before`
- `tg thread <chat> <message_id>` - View message with surrounding context; flag: `--context` (default 5)

## Design Constraints

- All output to stdout, errors to stderr
- Exit codes: 0 success, 1 error, 2 auth required
- Formatting functions are pure (no I/O)

## Key Conventions

- Use uv for dependency management and virtual environments
- pyproject.toml is the single source for project metadata and dependencies
- Use pytest and pytest-asyncio for testing; mock Telethon entirely, no real API calls
- Test each layer independently: config, auth, client, formatting, CLI integration (via `typer.testing.CliRunner`)
- Target Python >= 3.12

## When Editing

- Run `uv run pytest` to verify changes
- Keep CLI entrypoints thin; push logic into library modules
- Keep Telethon isolated from CLI and formatting layers
