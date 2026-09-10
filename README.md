# ✈️ tgcli — Telegram for your terminal and your AI agents.

Give AI agents (Claude Code, Codex, Cursor, etc.) direct access to your Telegram conversations. Structured JSONL output, minimal command surface, partial chat name matching. Works equally well for humans with `--pretty`.

## Features

- **JSONL by default** — one JSON object per line; agents parse it natively, scripts pipe it freely
- **Minimal surface** — a handful of commands; easy for agents to discover and invoke
- **Chat name resolution**: exact display names take priority; a unique substring also matches
- **`--pretty` for humans** — Rich tables when you want to read output yourself
- **Agent-friendly session storage** — Telethon session key stored in a local `0600` file by default; keychain remains available as a legacy option

## Installation

**One-liner** (installs [uv](https://docs.astral.sh/uv/) if needed):

```bash
curl -fsSL https://raw.githubusercontent.com/tksohishi/tgcli/main/install.sh | bash
```

**Homebrew:**

```bash
brew install tksohishi/tap/tgcli
```

**With uv:**

```bash
uv tool install pytgcli
```

**From source:**

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

This walks you through setup: saves your API credentials to `~/.config/tgcli/config.toml`, then logs in with phone number + verification code. The Telegram session is stored at `~/.config/tgcli/session` by default.

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

### 5. Download Attachments

```bash
tg media "Finance Team" 12345 --out ./downloads
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
set -o pipefail
tg read "Alerts" --limit 100 | jq 'select(.text | test("ERROR"))'
```

`pipefail` preserves a failed `tg read` exit status when `jq` succeeds. A chat lookup failure exits with code 1 and writes a human-readable error plus one JSON error line to stderr. Agents should check the exit status before treating empty stdout as “no messages.”

No wrapper libraries or API adapters needed. The structured output and simple command surface mean agents can use tgcli out of the box.

## Commands

### `tg auth`

Smart entrypoint: creates config if missing, logs in if needed, shows status if already authenticated.

Explicit subcommands:

- `tg auth login` - interactive login (phone + code/2FA)
- `tg auth logout` - remove the local session
- `tg auth migrate-session` - copy a legacy keychain session to the local session file
- `tg auth status` - show auth state

### `tg chats`

List your Telegram chats. Returns JSONL by default.

Each JSON object includes `id`, the Telethon dialog entity's numeric ID. Pass it to `read`, `context`, or `media` to skip name matching entirely:

```bash
tg chats --filter "Alice"
tg read 123456789 --limit 20
```

| Flag       | Description                  |
|------------|------------------------------|
| `--filter` | Case-insensitive substring filter by chat name |
| `--limit`  | Max dialogs to scan before filtering (default 100) |
| `--pretty` | Rich table output instead of JSONL |

Increase `--limit` if a chat is outside the scanned set.

### `tg read <chat>`

Read recent messages from a chat. Returns JSONL by default, newest first.

`<chat>` accepts a display name, `@username`, phone number, `me`, or numeric ID. Display names use case-insensitive exact matching first, then substring matching. A single substring match resolves automatically, so `tg read "Alice Morgan"` can open a DM named `Alice Morgan | Example Team`. It prints `Resolved "Alice Morgan" -> "Alice Morgan | Example Team"` on stderr, keeping stdout clean for pipes. Exact matches produce no resolution notice. Multiple substring matches fail with candidate names listed one per line. If no candidates exist, the error suggests `tg chats --filter`.

These lookup rules also apply to `context` and `media`. Numeric IDs, including negative group/channel IDs, skip name matching entirely. Put `--` before a negative positional ID so the CLI does not parse it as an option:

```bash
tg read --limit 20 -- -1001234567890
```

Lookup failures exit with code 1 and print both a human-readable message and a single JSON line to stderr. For an ambiguous name, the JSON looks like:

```json
{"error": "chat_not_found", "query": "Alice", "candidates": ["Alice Morgan | Example Team", "Alice Chen"]}
```

When no substring matches, similar spellings are offered as suggestions without opening a chat. `candidates` is an empty list when there are no suggestions.

| Flag           | Description                            |
|----------------|----------------------------------------|
| `--query`/`-q` | Filter messages by text                |
| `--from`       | Filter by sender                       |
| `--limit`      | Max messages (default 50)              |
| `--head`       | Oldest messages first                  |
| `--after`      | Only messages after date (YYYY-MM-DD)  |
| `--before`     | Only messages before date (YYYY-MM-DD) |
| `--pretty`     | Rich table output instead of JSONL     |

JSONL fields: `id`, `text`, `chat_name`, `sender_name`, `sender_username`, `sender_id`, `date`, `reply_to_msg_id`, `media_type`, `media_filename`. `media_type` is `null` or one of `photo`, `document`, `video`, `voice`, `sticker`, `webpage`, `other`; `media_filename` is the document's original filename when present. `--pretty` marks attachments with a `[photo]`-style tag.

### `tg media <chat> <message_id>`

Download the attachment of one message. Prints a single JSON line with `id`, `path`, and `media_type`. Fails when the message has no downloadable media (webpage previews count as no media) or the id is not found.

Only known media and document types are saved (images, video, audio, PDF, office files, text). Archives (zip, 7z, tar, gz, rar) need `--allow-archives`. Executables, scripts, installers, shortcuts, disk images, HTML, SVG, and XML are refused by extension and mime type. After the transfer, the file's leading and trailing bytes are checked too: Windows, ELF, and Mach-O binaries, shebang scripts, Windows shortcuts, cabinet and installer packages, DMG and ISO images, and archives or compound files renamed to a document extension are deleted and reported. Office documents with macros, RTF, and CSV are still saved; they are documents, not programs, so open them with the same care as any attachment. Attachments are refused before transfer when the reported size exceeds `--max-size` MB (default 100), and the transfer itself is cut off at that limit.

tgcli chooses the saved filename itself: `<message_id>_<sanitized original name>`, or `<media_type>_<message_id>.<ext>` when the message has no filename. It downloads into a staging file it created, never overwrites an existing file, and never follows a symlink in the output directory.

| Flag               | Description                            |
|--------------------|----------------------------------------|
| `--out`            | Directory to save into (default cwd)   |
| `--allow-archives` | Also download zip/7z/tar/gz/rar files  |
| `--max-size`       | Size limit in MB (default 100)         |

### `tg update`

Upgrade tgcli to the latest version. Detects the install method and runs the right command (or tells you what to run for Homebrew installs).

tgcli checks PyPI for new versions once per day and prints a notice to stderr when an update is available. Set `TGCLI_NO_UPDATE_CHECK=1` to disable.

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
session_store = "file"
```

`session_store` can be `file` or `keychain`. `file` is the default and stores the Telegram session at `~/.config/tgcli/session` with mode `0600`. `keychain` keeps the legacy system keychain behavior; it may trigger OS password prompts and will be removed in a future major release.

To migrate an existing keychain session to the file backend:

```bash
tg auth migrate-session
```

Add `--delete-keychain` to remove the keychain entry after a successful migration.

Alternatively, set `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and optionally `TGCLI_SESSION_STORE` environment variables.

## Contributing

```bash
uv sync --group dev
uv run pytest
uv run ruff check
```

Tests mock Telethon entirely; no real API calls are made.

## License

[MIT](LICENSE)
