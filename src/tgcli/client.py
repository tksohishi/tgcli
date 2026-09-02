from __future__ import annotations

import os
import re
import shutil
import zipfile
from datetime import datetime

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
)

from tgcli.config import TelegramConfig, load_config
from tgcli.formatting import ChatData, MessageData
from tgcli.media import (
    DEFAULT_MAX_BYTES,
    HEAD_SIZE,
    ISO_MARKER_OFFSET,
    TAIL_SIZE,
    content_reject_reason,
    reject_reason,
    target_filename,
)
from tgcli.session import load_session

_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def create_client(config: TelegramConfig | None = None) -> TelegramClient:
    """Create a TelegramClient using stored session and config."""
    config = config or load_config()
    session_str = load_session(store=config.session_store) or ""
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


def _get_username(entity) -> str | None:
    if entity is None:
        return None
    return getattr(entity, "username", None)


def _get_sender_id(msg, sender) -> int | None:
    sender_id = getattr(msg, "sender_id", None)
    if sender_id is not None:
        return sender_id
    if sender is None:
        return None
    return getattr(sender, "id", None)


def _is_entity_reference(value: str) -> bool:
    if value.startswith("@") or value.startswith("+") or value.lstrip("-").isdigit():
        return True
    return bool(_USERNAME_RE.fullmatch(value))


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


async def _resolve_sender(client: TelegramClient, chat_entity, value: str):
    """Resolve a sender filter within a chat."""
    if value.lower() == "me":
        return await client.get_me()

    sender_ref = value.strip()
    if _is_entity_reference(sender_ref):
        try:
            return await client.get_entity(sender_ref)
        except Exception:  # noqa: S110
            pass

    participant_search = sender_ref[1:] if sender_ref.startswith("@") else sender_ref
    username_query = participant_search.lower()
    display_matches = []
    async for participant in client.iter_participants(
        chat_entity, search=participant_search
    ):
        username = _get_username(participant)
        if username and username.lower() == username_query:
            return participant
        if _get_name(participant).lower() == sender_ref.lower():
            display_matches.append(participant)

    if len(display_matches) == 1:
        return display_matches[0]
    if len(display_matches) > 1:
        raise ValueError(
            f'Found multiple senders named "{value}". Use a username or numeric ID.'
        )
    raise ValueError(
        f'Cannot find sender "{value}" in this chat. Use username, numeric ID, '
        "or exact display name."
    )


def _media_info(media) -> tuple[str | None, str | None]:
    """Classify a Telethon media object as (media_type, filename)."""
    if media is None:
        return None, None
    if isinstance(media, MessageMediaPhoto):
        return "photo", None
    if isinstance(media, MessageMediaWebPage):
        return "webpage", None
    if not isinstance(media, MessageMediaDocument):
        return "other", None

    attrs = getattr(media.document, "attributes", None) or []
    filename = next(
        (a.file_name for a in attrs if isinstance(a, DocumentAttributeFilename)),
        None,
    )
    if any(isinstance(a, DocumentAttributeSticker) for a in attrs):
        return "sticker", filename
    if any(isinstance(a, DocumentAttributeAudio) and a.voice for a in attrs):
        return "voice", filename
    if any(isinstance(a, DocumentAttributeVideo) for a in attrs):
        return "video", filename
    return "document", filename


def _msg_to_data(msg, chat_name: str, sender) -> MessageData:
    media_type, media_filename = _media_info(getattr(msg, "media", None))
    return MessageData(
        id=msg.id,
        text=msg.text or "",
        chat_name=chat_name,
        sender_name=_get_name(sender),
        date=msg.date,
        sender_username=_get_username(sender),
        sender_id=_get_sender_id(msg, sender),
        reply_to_msg_id=msg.reply_to.reply_to_msg_id if msg.reply_to else None,
        media_type=media_type,
        media_filename=media_filename,
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
    async for dialog in client.iter_dialogs(limit=limit):
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
        from_user = await _resolve_sender(client, entity, from_)

    filtering = bool(query or from_user)
    filter_query = query.lower() if query else None
    offset_date = before if before and not reverse else None

    results: list[MessageData] = []
    async for msg in client.iter_messages(
        entity,
        limit=None if filtering else limit,
        offset_date=offset_date,
        reverse=reverse,
        from_user=from_user,
    ):
        if before and msg.date and msg.date >= before:
            if reverse:
                break
            continue

        if after and msg.date and msg.date < after:
            if reverse:
                continue
            break

        if filter_query and filter_query not in (msg.text or "").lower():
            continue

        sender = await msg.get_sender()
        results.append(_msg_to_data(msg, chat_name, sender))
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
        reverse=True,
    ):
        after_msgs.append(msg)

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
        messages.append(_msg_to_data(msg, chat_name, sender))

    # Find the replied-to message if applicable
    replied_to = None
    target_msg = next((m for m in messages_raw if m.id == message_id), None)
    if target_msg and target_msg.reply_to:
        reply_id = target_msg.reply_to.reply_to_msg_id
        reply_msg = await client.get_messages(entity, ids=reply_id)
        if reply_msg:
            sender = await reply_msg.get_sender()
            replied_to = _msg_to_data(reply_msg, chat_name, sender)

    return messages, message_id, replied_to


async def download_media(
    client: TelegramClient,
    chat: str,
    message_id: int,
    out_dir: str,
    *,
    allow_archives: bool = False,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> tuple[str, str]:
    """Download the attachment of one message into out_dir.

    Returns (saved_path, media_type). Raises ValueError when the message
    does not exist, has no downloadable media, or the attachment is refused
    by the safety rules in tgcli.media.

    The transfer goes into a staging file tgcli creates itself (so the
    sender never picks the path), is inspected, and only then linked to
    its final name. Anything that fails on the way is removed.
    """
    entity = await _resolve_entity(client, chat)
    msg = await client.get_messages(entity, ids=message_id)
    if msg is None:
        raise ValueError(f"Message {message_id} not found in this chat.")

    media = getattr(msg, "media", None)
    media_type, filename = _media_info(media)
    if media_type in (None, "webpage", "other"):
        raise ValueError(f"Message {message_id} has no downloadable media.")

    document = getattr(media, "document", None)
    mime_type = getattr(document, "mime_type", None) if document else None
    size = getattr(document, "size", None) if document else None
    if isinstance(size, int) and size > max_bytes:
        raise ValueError(
            f"Refusing to download message {message_id}: "
            f"{size} bytes exceeds the {max_bytes} byte limit."
        )

    name = target_filename(media_type, message_id, filename, mime_type)
    reason = reject_reason(name, mime_type, allow_archives=allow_archives)
    if reason:
        raise ValueError(f"Refusing to download message {message_id}: {reason}.")

    staged = os.path.join(out_dir, f".tgcli-{message_id}-{os.getpid()}.part")
    try:
        with open(staged, "xb") as f:
            writer = _BoundedWriter(f, max_bytes)
            await client.download_media(msg, file=writer)
        if writer.written == 0:
            raise ValueError(f"Message {message_id} has no downloadable media.")

        with open(staged, "rb") as f:
            head = f.read(HEAD_SIZE)
            f.seek(ISO_MARKER_OFFSET)
            iso_marker = f.read(5)
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - TAIL_SIZE))
            tail = f.read(TAIL_SIZE)
        zip_members = None
        if zipfile.is_zipfile(staged):
            try:
                with zipfile.ZipFile(staged) as zf:
                    zip_members = zf.namelist()
            except zipfile.BadZipFile:
                zip_members = None
        reason = content_reject_reason(
            name,
            head=head,
            tail=tail,
            iso_marker=iso_marker,
            zip_members=zip_members,
            allow_archives=allow_archives,
        )
        if reason:
            raise ValueError(f"Refusing to keep message {message_id}: {reason}.")

        final = _copy_unique(staged, os.path.join(out_dir, name))
    finally:
        if os.path.lexists(staged):
            os.remove(staged)
    return final, media_type


class _BoundedWriter:
    """File wrapper that aborts the transfer once max_bytes is exceeded.

    Telethon only needs write(), tell(), and flush(). The pre-transfer size
    check relies on the server-reported size; this bounds what actually
    lands on disk regardless of what the sender or server claims.
    """

    def __init__(self, f, max_bytes: int) -> None:
        self._f = f
        self._max = max_bytes
        self.written = 0

    def write(self, chunk) -> int:
        self.written += len(chunk)
        if self.written > self._max:
            raise ValueError(f"transfer exceeded the {self._max} byte limit")
        return self._f.write(chunk)

    def tell(self) -> int:
        return self._f.tell()

    def flush(self) -> None:
        self._f.flush()


def _copy_unique(src: str, dest: str) -> str:
    """Copy src to dest, adding a counter if dest already exists.

    The destination is created with O_EXCL (and O_NOFOLLOW where the
    platform has it), so an existing file or symlink of that name, even a
    dangling one, is never overwritten or followed. A plain copy is used
    instead of a hard link so exFAT and SMB output directories work.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    stem, ext = os.path.splitext(dest)
    candidate = dest
    for i in range(1, 1000):
        try:
            fd = os.open(candidate, flags, 0o644)
        except FileExistsError:
            candidate = f"{stem} ({i}){ext}"
            continue
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out)
        return candidate
    raise ValueError(f"Too many files named like {os.path.basename(dest)}.")
