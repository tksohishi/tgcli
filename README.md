# tgcli — Telegram in your terminal.

Search and read your Telegram messages from the command line. JSONL output by default for scripting; `--pretty` for human-readable tables.

## Features

- **Search** - full-text search across all chats, scoped with `--in` (chat) and `--from` (sender), plus date and limit filters
- **Read** - read recent messages from any chat
- **Context** - view any message with surrounding conversation
- **Fuzzy resolution** - chat and user names resolve via display name matching (no need for exact IDs)
- **JSONL output** - one JSON object per line, pipe-friendly; `--pretty` for Rich tables
- **1Password integration** - API credentials can be `op://` references resolved at runtime
- **Secure session storage** - Telethon session key stored in macOS Keychain via `keyring`

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install tgcli
```

Or install from source:

```bash
git clone https://github.com/tksohishi/tgcli.git
cd tgcli
uv tool install .
```

## Quick Start

### 1. Get API Credentials

Create a Telegram API app at [my.telegram.org/apps](https://my.telegram.org/apps). You'll get an `api_id` and `api_hash`.

### 2. Authenticate

```bash
tg auth
```

This walks you through setup: saves your API credentials to `~/.config/tgcli/config.toml`, then logs in with phone number + verification code.

### 3. Search

```bash
tg search "meeting notes"
tg search "budget" --in "Finance Team"
tg search --from me                     # your messages across all chats
tg search "deadline" --in "Finance Team" --from "Alice" --after 2025-01-01
```

### 4. Read Messages

```bash
tg read "Alice"
tg read "Finance Team" --limit 20
```

### 5. View Context

```bash
tg context "Finance Team" 12345
```

## Commands

### `tg auth`

Smart entrypoint: creates config if missing, logs in if needed, shows status if already authenticated.

Explicit subcommands:

- `tg auth login` - interactive login (phone + code/2FA)
- `tg auth logout` - remove session from Keychain
- `tg auth status` - show auth state

### `tg search [query]`

Search messages across chats. Returns JSONL by default. Query is optional when `--in` or `--from` is provided.

| Flag       | Description                            |
|------------|----------------------------------------|
| `--in`     | Chat or group to search within         |
| `--from`   | Filter by sender                       |
| `--limit`  | Max results (default 20)               |
| `--after`  | Only messages after date (YYYY-MM-DD)  |
| `--before` | Only messages before date (YYYY-MM-DD) |
| `--pretty` | Rich table output instead of JSONL     |

### `tg read <chat>`

Read recent messages from a chat. Returns JSONL by default, newest first.

| Flag       | Description                            |
|------------|----------------------------------------|
| `--limit`  | Max messages (default 50)              |
| `--head`   | Oldest messages first                  |
| `--after`  | Only messages after date (YYYY-MM-DD)  |
| `--before` | Only messages before date (YYYY-MM-DD) |
| `--pretty` | Rich table output instead of JSONL     |

### `tg context <chat> <message_id>`

View a message with surrounding context. Returns JSONL by default.

| Flag        | Description                       |
|-------------|-----------------------------------|
| `--context` | Messages before/after (default 5) |
| `--pretty`  | Rich text output instead of JSONL |

## Configuration

Config lives at `~/.config/tgcli/config.toml`:

```toml
api_id = 123456
api_hash = "your_api_hash"
```

Values can be [1Password CLI](https://developer.1password.com/docs/cli/) references:

```toml
api_id = "op://Personal/Telegram API/api_id"
api_hash = "op://Personal/Telegram API/api_hash"
```

Alternatively, set `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` environment variables.

## Contributing

```bash
uv sync --group dev
uv run pytest
uv run ruff check
```

Tests mock Telethon entirely; no real API calls are made.

## License

[MIT](LICENSE)
