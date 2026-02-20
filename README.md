# tg

CLI tool to search and read Telegram messages from the terminal.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install .
```

Or run directly from source:

```bash
uv run tg --help
```

## Quick Start

```bash
# Authenticate (prompts for API credentials if first run, then logs in)
tg auth

# Search messages
tg search "meeting notes"

# Search within a specific chat
tg search "budget" --chat "Finance Team"

# View a message with surrounding context
tg thread "Finance Team" 12345
```

Get your Telegram API credentials at [my.telegram.org/apps](https://my.telegram.org/apps).

## Commands

### `tg auth`

Smart entrypoint: creates config if missing, logs in if needed, shows status if already authenticated.

Explicit subcommands for scripting:

- `tg auth login`  -- interactive login (phone + code/2FA)
- `tg auth logout` -- remove session from Keychain
- `tg auth status` -- show auth state

### `tg search <query>`

Search messages across chats.

| Flag       | Description                          |
|------------|--------------------------------------|
| `--chat`   | Limit search to a specific chat      |
| `--from`   | Filter by sender name                |
| `--limit`  | Max results (default 20)             |
| `--after`  | Only messages after date (YYYY-MM-DD)|
| `--before` | Only messages before date (YYYY-MM-DD)|

### `tg thread <chat> <message_id>`

View a message with surrounding context.

| Flag        | Description                    |
|-------------|--------------------------------|
| `--context` | Messages before/after (default 5) |

## Configuration

Config lives at `~/.config/tgcli/config.toml`:

```toml
api_id = 123456
api_hash = "your_api_hash"
```

Values can also be [1Password CLI](https://developer.1password.com/docs/cli/) references:

```toml
api_id = "op://Personal/Telegram API/api_id"
api_hash = "op://Personal/Telegram API/api_hash"
```

Alternatively, set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` environment variables.

## Contributing

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/test_config.py -k test_write_config
```

Tests mock Telethon entirely; no real API calls are made.

## License

[MIT](LICENSE)
