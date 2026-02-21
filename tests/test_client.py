from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tg_cli.client import create_client, get_context, read_messages

_next_entity_id = 0


def _mock_entity(name: str, *, is_group: bool = False):
    global _next_entity_id
    _next_entity_id += 1
    e = SimpleNamespace(id=_next_entity_id)
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
    @patch("tg_cli.client.load_session", return_value="session_str")
    @patch("tg_cli.client.StringSession")
    @patch("tg_cli.client.TelegramClient")
    def test_creates_client_with_config(self, mock_tc, mock_ss, mock_load):
        from tg_cli.config import TelegramConfig

        cfg = TelegramConfig(api_id=123, api_hash="abc")
        create_client(cfg)

        mock_ss.assert_called_once_with("session_str")
        mock_tc.assert_called_once_with(mock_ss.return_value, 123, "abc")


class TestReadMessages:
    @pytest.fixture()
    def client(self):
        c = AsyncMock()
        group_dialog = _mock_dialog("Group")
        c.iter_dialogs = MagicMock(side_effect=lambda: _async_iter([group_dialog]))
        return c

    async def test_basic_read(self, client):
        msgs = [_mock_msg(1, "hello"), _mock_msg(2, "world")]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        results = await read_messages(client, "Group")

        assert len(results) == 2
        assert results[0].text == "hello"
        assert results[0].chat_name == "Group"
        assert results[1].text == "world"

    async def test_read_respects_limit(self, client):
        msgs = [_mock_msg(i, f"msg{i}") for i in range(5)]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        results = await read_messages(client, "Group", limit=3)

        assert len(results) == 3

    async def test_read_respects_after(self, client):
        old_date = datetime(2025, 1, 1, tzinfo=UTC)
        new_date = datetime(2025, 6, 1, tzinfo=UTC)
        msgs = [
            _mock_msg(1, "new", date=new_date),
            _mock_msg(2, "old", date=old_date),
        ]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))
        cutoff = datetime(2025, 3, 1, tzinfo=UTC)

        results = await read_messages(client, "Group", after=cutoff)

        assert len(results) == 1
        assert results[0].text == "new"

    async def test_read_resolves_entity(self, client):
        client.iter_messages = MagicMock(return_value=_async_iter([]))

        await read_messages(client, "Group")

        client.iter_dialogs.assert_called()

    async def test_read_reverse(self, client):
        msgs = [_mock_msg(1, "oldest"), _mock_msg(2, "newest")]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        results = await read_messages(client, "Group", reverse=True)

        assert len(results) == 2
        call_kwargs = client.iter_messages.call_args[1]
        assert call_kwargs["reverse"] is True

    async def test_read_reverse_before_filters_correctly(self, client):
        cutoff = datetime(2025, 3, 1, tzinfo=UTC)
        msgs = [
            _mock_msg(1, "jan", date=datetime(2025, 1, 1, tzinfo=UTC)),
            _mock_msg(2, "mar", date=datetime(2025, 3, 1, tzinfo=UTC)),
            _mock_msg(3, "apr", date=datetime(2025, 4, 1, tzinfo=UTC)),
        ]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        results = await read_messages(client, "Group", before=cutoff, reverse=True)

        call_kwargs = client.iter_messages.call_args[1]
        assert call_kwargs["offset_date"] is None
        assert [m.id for m in results] == [1]

    async def test_read_query_filters_client_side(self, client):
        msgs = [_mock_msg(1, "hello world"), _mock_msg(2, "goodbye")]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        results = await read_messages(client, "Group", query="hello")

        assert len(results) == 1
        assert results[0].text == "hello world"
        # limit=None when filtering
        call_kwargs = client.iter_messages.call_args[1]
        assert call_kwargs["limit"] is None

    async def test_read_query_case_insensitive(self, client):
        msgs = [_mock_msg(1, "Hello World"), _mock_msg(2, "goodbye")]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        results = await read_messages(client, "Group", query="hello")

        assert len(results) == 1
        assert results[0].text == "Hello World"

    async def test_read_from_resolves_sender(self, client):
        me_entity = _mock_entity("Takeshi")
        client.get_me = AsyncMock(return_value=me_entity)
        msgs = [_mock_msg(1, "my message")]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        results = await read_messages(client, "Group", from_="me")

        client.get_me.assert_called_once()
        call_kwargs = client.iter_messages.call_args[1]
        assert call_kwargs["from_user"] == me_entity
        assert call_kwargs["limit"] is None
        assert len(results) == 1

    async def test_read_query_and_from_combined(self, client):
        alice_dialog = _mock_dialog("Alice")
        client.iter_dialogs = MagicMock(
            side_effect=[
                _async_iter([_mock_dialog("Group")]),
                _async_iter([alice_dialog]),
            ]
        )
        match = _mock_msg(1, "hello world")
        miss = _mock_msg(2, "goodbye")
        client.iter_messages = MagicMock(return_value=_async_iter([match, miss]))

        results = await read_messages(client, "Group", query="hello", from_="Alice")

        assert len(results) == 1
        assert results[0].text == "hello world"
        call_kwargs = client.iter_messages.call_args[1]
        assert call_kwargs["from_user"] == alice_dialog.entity
        assert call_kwargs["limit"] is None

    async def test_read_no_query_no_from_passes_limit(self, client):
        msgs = [_mock_msg(1, "hello")]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        await read_messages(client, "Group", limit=10)

        call_kwargs = client.iter_messages.call_args[1]
        assert call_kwargs["limit"] == 10


class TestGetContext:
    @pytest.fixture()
    def client(self):
        c = AsyncMock()
        group_dialog = _mock_dialog("Group")
        c.iter_dialogs = MagicMock(side_effect=lambda: _async_iter([group_dialog]))
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

        messages, target_id, replied_to = await get_context(
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

        messages, target_id, _ = await get_context(client, "Group", 10, context=5)

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

        messages, target_id, replied_to = await get_context(
            client, "Group", 10, context=5
        )

        assert replied_to is not None
        assert replied_to.text == "original"

    async def test_after_side_uses_nearest_newer_messages(self, client):
        def iter_side_effect(*args, **kwargs):
            if kwargs.get("min_id"):
                if kwargs.get("reverse"):
                    return _async_iter(
                        [_mock_msg(11, "near11"), _mock_msg(12, "near12")]
                    )
                return _async_iter([_mock_msg(30, "far30"), _mock_msg(29, "far29")])
            return _async_iter([_mock_msg(10, "target"), _mock_msg(9, "before9")])

        client.iter_messages = MagicMock(side_effect=iter_side_effect)
        client.get_messages = AsyncMock(return_value=None)

        messages, _, _ = await get_context(client, "Group", 10, context=2)

        assert [m.id for m in messages] == [9, 10, 11, 12]
        after_call_kwargs = client.iter_messages.call_args_list[0][1]
        assert after_call_kwargs["reverse"] is True


def _mock_dialog(name: str, *, pinned: bool = False):
    entity = _mock_entity(name, is_group=True)
    return SimpleNamespace(name=name, pinned=pinned, entity=entity)


def _mock_iter_dialogs(*names: str):
    dialogs = [_mock_dialog(n) for n in names]
    return MagicMock(return_value=_async_iter(dialogs))


async def _async_iter(items):
    for item in items:
        yield item
