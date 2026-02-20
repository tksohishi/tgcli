from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tgcli.client import create_client, get_thread_context, search_messages


def _mock_entity(name: str, *, is_group: bool = False):
    e = SimpleNamespace()
    if is_group:
        e.title = name
    else:
        e.first_name = name
        e.last_name = None
    return e


def _mock_msg(
    id: int,
    text: str,
    *,
    chat_name: str = "Test Chat",
    sender_name: str = "Alice",
    is_group: bool = True,
    date: datetime | None = None,
    reply_to_msg_id: int | None = None,
):
    msg = AsyncMock()
    msg.id = id
    msg.text = text
    msg.date = date or datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
    msg.reply_to = (
        SimpleNamespace(reply_to_msg_id=reply_to_msg_id) if reply_to_msg_id else None
    )
    msg.get_chat = AsyncMock(return_value=_mock_entity(chat_name, is_group=is_group))
    msg.get_sender = AsyncMock(return_value=_mock_entity(sender_name))
    return msg


class TestCreateClient:
    @patch("tgcli.client.load_session", return_value="session_str")
    @patch("tgcli.client.StringSession")
    @patch("tgcli.client.TelegramClient")
    def test_creates_client_with_config(self, mock_tc, mock_ss, mock_load):
        from tgcli.config import TelegramConfig

        cfg = TelegramConfig(api_id=123, api_hash="abc")
        create_client(cfg)

        mock_ss.assert_called_once_with("session_str")
        mock_tc.assert_called_once_with(mock_ss.return_value, 123, "abc")


class TestSearchMessages:
    @pytest.fixture()
    def client(self):
        c = AsyncMock()
        return c

    async def test_basic_search(self, client):
        msgs = [_mock_msg(1, "found it"), _mock_msg(2, "also here")]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        results = await search_messages(client, "found")

        assert len(results) == 2
        assert results[0].text == "found it"
        assert results[0].id == 1
        assert results[1].text == "also here"

    async def test_search_with_chat(self, client):
        chat_entity = _mock_entity("Work", is_group=True)
        client.get_entity = AsyncMock(return_value=chat_entity)
        client.iter_messages = MagicMock(return_value=_async_iter([]))

        await search_messages(client, "q", chat="Work")

        client.get_entity.assert_called_with("Work")

    async def test_search_respects_after(self, client):
        old_date = datetime(2025, 1, 1, tzinfo=UTC)
        new_date = datetime(2025, 6, 1, tzinfo=UTC)
        msgs = [
            _mock_msg(1, "new", date=new_date),
            _mock_msg(2, "old", date=old_date),
        ]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))
        cutoff = datetime(2025, 3, 1, tzinfo=UTC)

        results = await search_messages(client, "q", after=cutoff)

        assert len(results) == 1
        assert results[0].text == "new"


class TestGetThreadContext:
    @pytest.fixture()
    def client(self):
        c = AsyncMock()
        c.get_entity = AsyncMock(return_value=_mock_entity("Group", is_group=True))
        return c

    async def test_returns_messages_around_target(self, client):
        target = _mock_msg(10, "target")
        before = _mock_msg(9, "before")
        after = _mock_msg(11, "after")

        def iter_side_effect(*args, **kwargs):
            if kwargs.get("min_id"):
                return _async_iter([after])
            return _async_iter([target, before])

        client.iter_messages = MagicMock(side_effect=iter_side_effect)
        client.get_messages = AsyncMock(return_value=None)

        messages, target_id, replied_to = await get_thread_context(
            client, "Group", 10, context=5
        )

        assert target_id == 10
        assert any(m.id == 10 for m in messages)
        assert replied_to is None

    async def test_messages_in_chronological_order(self, client):
        """Messages should be returned sorted by ID (chronological)."""

        # iter_messages returns newest-first; the function must sort them
        def iter_side_effect(*args, **kwargs):
            if kwargs.get("min_id"):
                # Newer messages: 13, 12, 11 (newest first from API)
                return _async_iter(
                    [
                        _mock_msg(13, "msg13"),
                        _mock_msg(12, "msg12"),
                        _mock_msg(11, "msg11"),
                    ]
                )
            # Target + older: 10, 9, 8 (newest first from API)
            return _async_iter(
                [
                    _mock_msg(10, "target"),
                    _mock_msg(9, "msg9"),
                    _mock_msg(8, "msg8"),
                ]
            )

        client.iter_messages = MagicMock(side_effect=iter_side_effect)
        client.get_messages = AsyncMock(return_value=None)

        messages, target_id, _ = await get_thread_context(
            client, "Group", 10, context=5
        )

        ids = [m.id for m in messages]
        assert ids == sorted(ids), f"Messages not chronological: {ids}"

    async def test_includes_replied_to(self, client):
        target = _mock_msg(10, "reply", reply_to_msg_id=5)
        reply_source = _mock_msg(5, "original")

        client.iter_messages = MagicMock(
            side_effect=[
                _async_iter([]),  # after
                _async_iter([target]),  # before + target
            ]
        )
        client.get_messages = AsyncMock(return_value=reply_source)

        messages, target_id, replied_to = await get_thread_context(
            client, "Group", 10, context=5
        )

        assert replied_to is not None
        assert replied_to.text == "original"


async def _async_iter(items):
    for item in items:
        yield item
