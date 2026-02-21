from __future__ import annotations

from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession

from tgcli.config import TelegramConfig, load_config
from tgcli.formatting import MessageData
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

    Tries get_entity() first (handles usernames, IDs, phone numbers),
    then falls back to fuzzy display name matching via iter_dialogs().
    """
    try:
        return await client.get_entity(name)
    except Exception:  # noqa: S110
        pass

    name_lower = name.lower()
    async for dialog in client.iter_dialogs():
        if name_lower in dialog.name.lower():
            return dialog.entity

    raise ValueError(f'Cannot find any chat or user matching "{name}"')


def _msg_to_data(msg, chat_name: str, sender_name: str) -> MessageData:
    return MessageData(
        id=msg.id,
        text=msg.text or "",
        chat_name=chat_name,
        sender_name=sender_name,
        date=msg.date,
        reply_to_msg_id=msg.reply_to.reply_to_msg_id if msg.reply_to else None,
    )


async def search_messages(
    client: TelegramClient,
    query: str = "",
    *,
    in_: str | None = None,
    from_: str | None = None,
    limit: int = 20,
    after: datetime | None = None,
    before: datetime | None = None,
) -> list[MessageData]:
    """Search messages, optionally scoped to a chat and/or sender."""
    entity = None
    from_user = None
    if in_:
        entity = await _resolve_entity(client, in_)
        if from_:
            from_user = await _resolve_entity(client, from_)
    elif from_:
        entity = await _resolve_entity(client, from_)

    results: list[MessageData] = []
    async for msg in client.iter_messages(
        entity,
        search=query,
        limit=limit,
        offset_date=before,
        from_user=from_user,
    ):
        if after and msg.date and msg.date < after:
            break

        chat_entity = await msg.get_chat()
        sender = await msg.get_sender()
        sender_name = _get_name(sender)

        results.append(_msg_to_data(msg, _get_name(chat_entity), sender_name))
        if len(results) >= limit:
            break

    return results


async def read_messages(
    client: TelegramClient,
    chat: str,
    *,
    limit: int = 50,
    after: datetime | None = None,
    before: datetime | None = None,
    reverse: bool = False,
) -> list[MessageData]:
    """Read messages from a chat.

    Default order is newest first (tail). Set reverse=True for oldest first (head).
    """
    entity = await _resolve_entity(client, chat)
    chat_name = _get_name(entity)

    results: list[MessageData] = []
    async for msg in client.iter_messages(
        entity,
        limit=limit,
        offset_date=before,
        reverse=reverse,
    ):
        if after and msg.date and msg.date < after:
            if reverse:
                continue
            break

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
