# ✈️ tgcli — Telegram for your terminal and your AI agents.

Give AI agents (Claude Code, Codex, Cursor, etc.) direct access to your Telegram conversations. Structured JSONL output, minimal command surface, fuzzy name resolution. Works equally well for humans with `--pretty`.

## Features

- **JSONL by default** — one JSON object per line; agents parse it natively, scripts pipe it freely
- **Minimal surface** — a handful of commands; easy for agents to discover and invoke
- **Fuzzy resolution** — chat and user names match by display name (no numeric IDs required)
- **`--pretty` for humans** — Rich tables when you want to read output yourself
- **Secure session storage** — Telethon session key stored in system keychain via `keyring`

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv tool install pytgcli
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

### 3. Read Messages

```bash
tg read "Alice"
tg read "Finance Team" --limit 20
tg read "Finance Team" -q "budget"
tg read "Finance Team" -q "deadline" --from "Alice" --after 2025-01-01
```

### 4. View Context

```bash
tg context "Finance Team" 12345
```

## Use with AI Agents

Once authenticated, any AI coding agent with shell access can use tgcli directly. A few examples:

**Ask Claude Code to summarize a group chat:**

> "Read the last 30 messages from 'Engineering' and summarize the key decisions."

The agent runs `tg read "Engineering" --limit 30`, parses the JSONL, and responds.

**Find a past conversation:**

> "What did I discuss with Alice last week about the deployment?"

The agent runs `tg read "Alice" -q "deployment" --after 2025-02-14` and surfaces the relevant messages.

**Pipe into scripts:**

```bash
tg read "Alerts" --limit 100 | jq 'select(.text | test("ERROR"))'
```

No wrapper libraries or API adapters needed. The structured output and simple command surface mean agents can use tgcli out of the box.

## Commands

### `tg auth`

Smart entrypoint: creates config if missing, logs in if needed, shows status if already authenticated.

Explicit subcommands:

- `tg auth login` - interactive login (phone + code/2FA)
- `tg auth logout` - remove session from system keychain
- `tg auth status` - show auth state

### `tg chats`

List your Telegram chats. Returns JSONL by default.

| Flag       | Description                  |
|------------|------------------------------|
| `--filter` | Fuzzy filter by chat name    |
| `--limit`  | Max chats to list (default 100) |
| `--pretty` | Rich table output instead of JSONL |

### `tg read <chat>`

Read recent messages from a chat. Returns JSONL by default, newest first.

| Flag           | Description                            |
|----------------|----------------------------------------|
| `--query`/`-q` | Filter messages by text                |
| `--from`       | Filter by sender                       |
| `--limit`      | Max messages (default 50)              |
| `--head`       | Oldest messages first                  |
| `--after`      | Only messages after date (YYYY-MM-DD)  |
| `--before`     | Only messages before date (YYYY-MM-DD) |
| `--pretty`     | Rich table output instead of JSONL     |

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
