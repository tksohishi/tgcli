from __future__ import annotations

from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession

from tgcli.config import TelegramConfig, load_config
from tgcli.formatting import ChatData, MessageData
from tgcli.session import load_session


def create_client(config: TelegramConfig | None = None) -> TelegramClient:
    """Create a TelegramClient using stored session and config."""
    config = config or load_config()
    session_str = load_session() or ""
    return TelegramClient(
        StringSession(session_str),
        config.api_id,
        config.api_hash,
    )


def _get_name(entity) -> str:
    """Extract a display name from a Telethon entity."""
    if entity is None:
        return "Unknown"
    if hasattr(entity, "title"):
        return entity.title
    parts = [getattr(entity, "first_name", None), getattr(entity, "last_name", None)]
    return " ".join(p for p in parts if p) or "Unknown"


async def _resolve_entity(client: TelegramClient, name: str):
    """Resolve a name to a Telethon entity.

    Handles @usernames, phone numbers, and numeric IDs via get_entity().
    Plain names are matched case-insensitively against dialog names.
    """
    if name.lower() == "me":
        return await client.get_me()

    if name.startswith("@") or name.startswith("+") or name.lstrip("-").isdigit():
        try:
            return await client.get_entity(name)
        except Exception:  # noqa: S110
            pass

    name_lower = name.lower()
    async for dialog in client.iter_dialogs():
        if dialog.name.lower() == name_lower:
            return dialog.entity

    raise ValueError(
        f'Cannot find chat "{name}". Use `tg chats --filter` to find exact names.'
    )


def _msg_to_data(msg, chat_name: str, sender_name: str) -> MessageData:
    return MessageData(
        id=msg.id,
        text=msg.text or "",
        chat_name=chat_name,
        sender_name=sender_name,
        date=msg.date,
        reply_to_msg_id=msg.reply_to.reply_to_msg_id if msg.reply_to else None,
    )


def _chat_type(entity) -> str:
    """Determine the chat type from a Telethon entity."""
    cls = type(entity).__name__
    if cls == "User":
        return "user"
    if cls == "Channel":
        if getattr(entity, "megagroup", False):
            return "group"
        return "channel"
    return "group"


async def list_chats(
    client: TelegramClient,
    *,
    filter_name: str | None = None,
    limit: int = 100,
) -> list[ChatData]:
    """List dialogs, optionally filtered by name substring.

    limit controls how many dialogs to scan. With filter_name, matches
    are returned from that scanned set.
    """
    filter_lower = filter_name.lower() if filter_name else None
    results: list[ChatData] = []
    count = 0
    async for dialog in client.iter_dialogs():
        count += 1
        if not filter_lower or filter_lower in dialog.name.lower():
            results.append(
                ChatData(
                    name=dialog.name,
                    chat_type=_chat_type(dialog.entity),
                    unread_count=dialog.unread_count,
                    pinned=dialog.pinned,
                    date=dialog.date,
                )
            )
        if count >= limit:
            break
    return results


async def read_messages(
    client: TelegramClient,
    chat: str,
    *,
    query: str = "",
    from_: str | None = None,
    limit: int = 50,
    after: datetime | None = None,
    before: datetime | None = None,
    reverse: bool = False,
) -> list[MessageData]:
    """Read messages from a chat.

    Default order is newest first (tail). Set reverse=True for oldest first (head).
    Optional query does client-side text filtering. Optional from_ filters by sender
    (resolved server-side via from_user).
    """
    entity = await _resolve_entity(client, chat)
    chat_name = _get_name(entity)

    from_user = None
    if from_:
        from_user = await _resolve_entity(client, from_)

    filtering = bool(query or from_user)
    filter_query = query.lower() if query else None

    results: list[MessageData] = []
    async for msg in client.iter_messages(
        entity,
        limit=None if filtering else limit,
        offset_date=before,
        reverse=reverse,
        from_user=from_user,
    ):
        if after and msg.date and msg.date < after:
            if reverse:
                continue
            break

        if filter_query and filter_query not in (msg.text or "").lower():
            continue

        sender = await msg.get_sender()
        results.append(_msg_to_data(msg, chat_name, _get_name(sender)))
        if len(results) >= limit:
            break

    return results


async def get_context(
    client: TelegramClient,
    chat: str,
    message_id: int,
    context: int = 5,
) -> tuple[list[MessageData], int, MessageData | None]:
    """Get a message and surrounding context.

    Returns (messages, target_id, replied_to_message).
    """
    entity = await _resolve_entity(client, chat)
    chat_name = _get_name(entity)

    # Fetch messages around the target: context after + target + context before
    # iter_messages returns newest first, so offset from message_id
    messages_raw = []

    # Messages after (newer than) the target
    after_msgs = []
    async for msg in client.iter_messages(
        entity,
        min_id=message_id,
        limit=context,
    ):
        after_msgs.append(msg)
    after_msgs.reverse()

    # The target message itself + messages before (older than) it
    before_msgs = []
    async for msg in client.iter_messages(
        entity,
        max_id=message_id + 1,
        limit=context + 1,
    ):
        before_msgs.append(msg)

    messages_raw = sorted(after_msgs + before_msgs, key=lambda m: m.id)

    # Build MessageData list
    messages: list[MessageData] = []
    for msg in messages_raw:
        sender = await msg.get_sender()
        messages.append(_msg_to_data(msg, chat_name, _get_name(sender)))

    # Find the replied-to message if applicable
    replied_to = None
    target_msg = next((m for m in messages_raw if m.id == message_id), None)
    if target_msg and target_msg.reply_to:
        reply_id = target_msg.reply_to.reply_to_msg_id
        reply_msg = await client.get_messages(entity, ids=reply_id)
        if reply_msg:
            sender = await reply_msg.get_sender()
            replied_to = _msg_to_data(reply_msg, chat_name, _get_name(sender))

    return messages, message_id, replied_to
