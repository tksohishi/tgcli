from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tgcli.formatting import MessageData


@pytest.fixture(autouse=True)
def _suppress_update_check(monkeypatch):
    """Prevent real PyPI calls during tests."""
    monkeypatch.setenv("TGCLI_NO_UPDATE_CHECK", "1")


def _make_message(
    *,
    id: int = 1,
    text: str = "hello",
    chat_name: str = "Test Chat",
    sender_name: str = "Alice",
    date: datetime | None = None,
    reply_to_msg_id: int | None = None,
) -> MessageData:
    return MessageData(
        id=id,
        text=text,
        chat_name=chat_name,
        sender_name=sender_name,
        date=date or datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        reply_to_msg_id=reply_to_msg_id,
    )


@pytest.fixture()
def make_message():
    """Factory fixture for creating MessageData instances."""
    return _make_message


async def async_iter(items):
    """Wrap a list into an async iterator (mimics Telethon's async generators)."""
    for item in items:
        yield item
