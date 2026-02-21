# AGENTS.md

## Architecture

```
src/tgcli/
  cli.py          # Typer app, thin entrypoints
  auth.py         # Login/logout/status logic
  client.py       # Telethon wrapper (search, read, context)
  config.py       # Config loading (TOML + env vars)
  formatting.py   # Pure output formatting functions (no I/O)
  session.py      # Keychain-backed StringSession via keyring
tests/              # pytest + pytest-asyncio, Telethon fully mocked
```

Layers: CLI (Typer) -> business logic (auth, client) -> Telethon.

## Constraints

- Keep Telethon isolated from CLI and formatting layers
- Keep CLI entrypoints thin; push logic into library modules
- Formatting functions are pure (no I/O)
- All output to stdout, errors to stderr
- Exit codes: 0 success, 1 error, 2 auth required
- Mock Telethon entirely in tests, no real API calls

## Telethon Reference

For Telethon questions (API methods, entity resolution, session handling, etc.), check https://docs.telethon.dev/en/stable/ first.

## Verify

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```
