from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime

from rich.table import Table
from rich.text import Text


@dataclass(frozen=True)
class ChatData:
    name: str
    chat_type: str
    unread_count: int
    pinned: bool
    date: datetime | None


@dataclass(frozen=True)
class MessageData:
    id: int
    text: str
    chat_name: str
    sender_name: str
    date: datetime
    reply_to_msg_id: int | None = None


def _truncate(text: str, max_lines: int = 3) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + " ..."


def format_message_jsonl(msg: MessageData, **flags: bool) -> str:
    """Serialize a MessageData to a single JSON line.

    Extra boolean flags (e.g. target=True, replied_to=True) are merged
    into the dict before serialization.
    """
    d = asdict(msg)
    d["date"] = msg.date.isoformat()
    for key, value in flags.items():
        if value:
            d[key] = True
    return json.dumps(d, ensure_ascii=False)


def format_search_results(messages: list[MessageData]) -> Table:
    """Build a Rich Table for search results."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Date", style="dim", no_wrap=True)
    table.add_column("Chat")
    table.add_column("Sender")
    table.add_column("Message")

    for msg in messages:
        table.add_row(
            msg.date.strftime("%Y-%m-%d %H:%M"),
            msg.chat_name,
            msg.sender_name,
            _truncate(msg.text),
        )

    return table


def format_context(
    messages: list[MessageData],
    target_id: int,
    replied_to: MessageData | None = None,
) -> Text:
    """Build a Rich Text for context view.

    The target message is highlighted. If replied_to is provided, it's
    shown above the target with a separator.
    """
    output = Text()

    if replied_to:
        output.append(
            f"  >> {replied_to.sender_name}: {replied_to.text}\n",
            style="dim italic",
        )
        output.append("  " + "-" * 40 + "\n", style="dim")

    for msg in messages:
        ts = msg.date.strftime("%H:%M")
        line = f"[{ts}] {msg.sender_name}: {msg.text}\n"
        if msg.id == target_id:
            output.append(line, style="bold yellow")
        else:
            output.append(line)

    return output


def format_chat_line(chat: ChatData) -> str:
    """Format a chat as a single line: name."""
    return chat.name


def format_chat_jsonl(chat: ChatData) -> str:
    """Serialize a ChatData to a single JSON line."""
    d = asdict(chat)
    if chat.date:
        d["date"] = chat.date.isoformat()
    return json.dumps(d, ensure_ascii=False)


def format_chats_table(chats: list[ChatData]) -> Table:
    """Build a Rich Table for chat listing."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Type", style="dim")
    table.add_column("Unread", justify="right")
    table.add_column("Last message", style="dim", no_wrap=True)

    for chat in chats:
        unread = str(chat.unread_count) if chat.unread_count else ""
        date = chat.date.strftime("%Y-%m-%d") if chat.date else ""
        table.add_row(chat.name, chat.chat_type, unread, date)

    return table


def format_auth_status(
    authenticated: bool,
    phone: str | None = None,
    session_exists: bool = False,
) -> Text:
    """Build a Rich Text for auth status display."""
    output = Text()

    if authenticated:
        output.append("Status: ", style="bold")
        output.append("authenticated\n", style="green")
    else:
        output.append("Status: ", style="bold")
        output.append("not authenticated\n", style="red")

    if phone:
        output.append("Phone: ", style="bold")
        output.append(f"{phone}\n")

    output.append("Session: ", style="bold")
    if session_exists:
        output.append("stored in Keychain\n", style="green")
    else:
        output.append("none\n", style="red")

    return output
