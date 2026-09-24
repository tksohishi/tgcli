from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tgcli.client import (
    ChatResolutionError,
    _resolve_entity,
    create_client,
    get_context,
    list_chats,
    read_messages,
)

_next_entity_id = 0


def _mock_entity(
    name: str,
    *,
    is_group: bool = False,
    username: str | None = None,
    id: int | None = None,
):
    global _next_entity_id
    if id is None:
        _next_entity_id += 1
        id = _next_entity_id
    e = SimpleNamespace(id=id)
    if is_group:
        e.title = name
    else:
        e.first_name = name
        e.last_name = None
        e.username = username
    return e


def _mock_msg(
    id: int,
    text: str,
    *,
    chat_name: str = "Test Chat",
    sender_name: str = "Alice",
    sender_username: str | None = None,
    sender_id: int | None = None,
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
    sender = _mock_entity(sender_name, username=sender_username, id=sender_id)
    msg.sender_id = sender.id
    msg.get_sender = AsyncMock(return_value=sender)
    return msg


class TestCreateClient:
    @patch("tgcli.client.load_session", return_value="session_str")
    @patch("tgcli.client.StringSession")
    @patch("tgcli.client.TelegramClient")
    def test_creates_client_with_config(self, mock_tc, mock_ss, mock_load):
        from tgcli.config import TelegramConfig

        cfg = TelegramConfig(api_id=123, api_hash="abc")
        create_client(cfg)

        mock_load.assert_called_once_with(store="file")
        mock_ss.assert_called_once_with("session_str")
        mock_tc.assert_called_once_with(mock_ss.return_value, 123, "abc")


class TestResolveEntity:
    @pytest.fixture()
    def client(self):
        client = AsyncMock()
        client.get_entity.side_effect = ValueError("not found")
        client.iter_dialogs = _mock_iter_dialogs()
        return client

    async def test_exact_match_precedes_substrings(self, client, capsys):
        dialogs = [_mock_dialog("Mira Vale | Example"), _mock_dialog("Mira Vale")]
        client.iter_dialogs = MagicMock(return_value=_async_iter(dialogs))

        assert await _resolve_entity(client, "mIRA vALE") is dialogs[1].entity
        client.iter_dialogs.assert_called_once_with()
        client.get_entity.assert_not_awaited()
        assert capsys.readouterr() == ("", "")

    async def test_unique_substring_is_case_insensitive(self, client, capsys):
        dialogs = [_mock_dialog("Other"), _mock_dialog("Mira Vale | Example")]
        client.iter_dialogs = MagicMock(return_value=_async_iter(dialogs))

        assert await _resolve_entity(client, "mIRA vALE") is dialogs[1].entity
        client.iter_dialogs.assert_called_once_with()
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == 'Resolved "mIRA vALE" -> "Mira Vale | Example"\n'

    async def test_resolution_notice_escapes_names_on_one_line(self, client, capsys):
        query = 'Mira "[red]" \\ 雪\n'
        client.iter_dialogs = _mock_iter_dialogs(query + "Example")

        await _resolve_entity(client, query)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == (
            'Resolved "Mira \\"[red]\\" \\\\ 雪\\n" -> '
            '"Mira \\"[red]\\" \\\\ 雪\\nExample"\n'
        )

    async def test_ambiguous_substring_lists_candidates(self, client):
        candidates = ["Mira Vale | Example", "Mira Vale | Studio"]
        client.iter_dialogs = _mock_iter_dialogs(*candidates)

        with pytest.raises(ChatResolutionError) as caught:
            await _resolve_entity(client, "Mira Vale")

        assert caught.value.query == "Mira Vale"
        assert caught.value.candidates == candidates
        assert 'Cannot find chat "Mira Vale". Did you mean:' in str(caught.value)
        assert '\n"Mira Vale | Example"' in str(caught.value)
        assert '\n"Mira Vale | Studio"' in str(caught.value)
        client.iter_dialogs.assert_called_once_with()

    async def test_no_match_keeps_discovery_hint(self, client):
        client.iter_dialogs = _mock_iter_dialogs("Project Alpha")

        with pytest.raises(ChatResolutionError) as caught:
            await _resolve_entity(client, "zzzzzz")

        assert caught.value.query == "zzzzzz"
        assert caught.value.candidates == []
        assert 'Cannot find chat "zzzzzz".' in str(caught.value)
        assert "Use `tg chats --filter`" in str(caught.value)
        client.iter_dialogs.assert_called_once_with()

    async def test_near_match_suggested_but_never_resolved(self, client):
        client.iter_dialogs = _mock_iter_dialogs("Mira Vale", "Project Alpha")

        with pytest.raises(ChatResolutionError) as caught:
            await _resolve_entity(client, "mira vlae")

        assert caught.value.candidates == ["Mira Vale"]
        assert "Did you mean:" in str(caught.value)
        client.iter_dialogs.assert_called_once_with()

    @pytest.mark.parametrize("query", ["@mira_example", "+12025550123"])
    async def test_direct_reference_precedes_names(self, client, query):
        client.get_entity.side_effect = None
        entity = client.get_entity.return_value

        assert await _resolve_entity(client, query) is entity
        client.get_entity.assert_awaited_once_with(query)
        client.iter_dialogs.assert_not_called()

    async def test_me_uses_current_user(self, client):
        assert await _resolve_entity(client, "ME") is client.get_me.return_value
        client.get_me.assert_awaited_once_with()
        client.iter_dialogs.assert_not_called()

    async def test_invalid_username_becomes_resolution_error(self, client):
        from telethon.errors import UsernameInvalidError

        client.get_entity.side_effect = UsernameInvalidError(None)

        with pytest.raises(ChatResolutionError) as caught:
            await _resolve_entity(client, "@invalid_username")

        assert caught.value.query == "@invalid_username"
        assert caught.value.candidates == []

    @pytest.mark.parametrize("query", ["123", "-123", "-1000000000123"])
    async def test_numeric_reference_is_passed_as_integer(self, client, query):
        client.get_entity.side_effect = None

        assert await _resolve_entity(client, query) is client.get_entity.return_value
        client.get_entity.assert_awaited_once_with(int(query))
        client.iter_dialogs.assert_not_called()

    @pytest.mark.parametrize("query", ["123", "-123", "-1000000000123"])
    async def test_uncached_id_resolves_from_dialog(self, client, query):
        dialog = _mock_dialog("Mira Vale")
        dialog.entity.id = 123
        dialog.id = int(query) if query.startswith("-") else -123
        client.iter_dialogs = MagicMock(return_value=_async_iter([dialog]))

        assert await _resolve_entity(client, query) is dialog.entity
        client.get_entity.assert_awaited_once_with(int(query))
        client.iter_dialogs.assert_called_once_with()

    async def test_missing_numeric_id_never_matches_name(self, client):
        dialog = _mock_dialog("999999999")
        dialog.entity.id = 123
        dialog.id = -123
        client.iter_dialogs = MagicMock(return_value=_async_iter([dialog]))

        with pytest.raises(ChatResolutionError) as caught:
            await _resolve_entity(client, "999999999")

        assert caught.value.candidates == []

    async def test_empty_chat_is_a_resolution_failure(self, client):
        from telethon.tl.types import ChatEmpty

        client.get_entity.side_effect = None
        client.get_entity.return_value = ChatEmpty(id=123)

        with pytest.raises(ChatResolutionError) as caught:
            await _resolve_entity(client, "-123")

        assert caught.value.query == "-123"
        assert caught.value.candidates == []

    async def test_authorization_errors_are_not_resolution_errors(self, client):
        from telethon.errors import UnauthorizedError

        client.get_entity.side_effect = UnauthorizedError(None, None)
        with pytest.raises(UnauthorizedError):
            await _resolve_entity(client, "123")
        client.iter_dialogs.assert_not_called()


class TestListChats:
    async def test_json_id_uses_entity_id_and_filter_matches_substring(self):
        dialog = _mock_dialog("Mira Vale | Example")
        dialog.entity.id = 123
        dialog.id = -1000000000123
        dialog.unread_count = 2
        dialog.date = None
        client = AsyncMock()
        client.iter_dialogs = MagicMock(return_value=_async_iter([dialog]))

        chats = await list_chats(client, filter_name="mIRA vALE")

        assert len(chats) == 1
        assert chats[0].id == 123
        assert chats[0].name == dialog.name


class TestReadMessages:
    @pytest.fixture()
    def client(self):
        c = AsyncMock()
        group_dialog = _mock_dialog("Group")
        c.iter_dialogs = MagicMock(side_effect=lambda: _async_iter([group_dialog]))
        c.get_entity = AsyncMock(side_effect=ValueError("not found"))
        c.iter_participants = MagicMock(return_value=_async_iter([]))
        return c

    async def test_basic_read(self, client):
        msgs = [
            _mock_msg(1, "hello", sender_username="alice", sender_id=1001),
            _mock_msg(2, "world"),
        ]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))

        results = await read_messages(client, "Group")

        assert len(results) == 2
        assert results[0].text == "hello"
        assert results[0].chat_name == "Group"
        assert results[0].sender_name == "Alice"
        assert results[0].sender_username == "alice"
        assert results[0].sender_id == 1001
        assert results[1].text == "world"
        assert results[1].sender_username is None

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

    async def test_read_query_scan_cap_stops_walk(self, client):
        dates = [
            datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(10)
        ]
        msgs = [
            _mock_msg(i, "hello" if i == 1 else "other", date=dates[9 - i])
            for i in range(10)
        ]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))
        cap_calls = []

        results = await read_messages(
            client,
            "Group",
            query="hello",
            scan=3,
            on_scan_cap=lambda *a: cap_calls.append(a),
        )

        assert [m.id for m in results] == [1]
        assert cap_calls == [(3, dates[7])]

    async def test_read_query_scan_cap_not_hit_at_exact_count(self, client):
        msgs = [_mock_msg(i, "other") for i in range(3)]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))
        cap_calls = []

        results = await read_messages(
            client,
            "Group",
            query="hello",
            scan=3,
            on_scan_cap=lambda *a: cap_calls.append(a),
        )

        assert results == []
        assert cap_calls == []

    async def test_read_query_scan_cap_ignored_with_after(self, client):
        msgs = [
            _mock_msg(i, "other", date=datetime(2025, 6, 1, tzinfo=UTC))
            for i in range(5)
        ]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))
        cap_calls = []

        results = await read_messages(
            client,
            "Group",
            query="hello",
            scan=2,
            after=datetime(2025, 1, 1, tzinfo=UTC),
            on_scan_cap=lambda *a: cap_calls.append(a),
        )

        assert results == []
        assert cap_calls == []

    async def test_read_scan_cap_ignored_without_filter(self, client):
        msgs = [_mock_msg(i, f"msg{i}") for i in range(5)]
        client.iter_messages = MagicMock(return_value=_async_iter(msgs))
        cap_calls = []

        results = await read_messages(
            client, "Group", scan=2, on_scan_cap=lambda *a: cap_calls.append(a)
        )

        assert len(results) == 5
        assert cap_calls == []

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
        alice = _mock_entity("Alice", username="alice_user", id=100)
        client.iter_participants = MagicMock(return_value=_async_iter([alice]))
        match = _mock_msg(1, "hello world")
        miss = _mock_msg(2, "goodbye")
        client.iter_messages = MagicMock(return_value=_async_iter([match, miss]))

        results = await read_messages(client, "Group", query="hello", from_="Alice")

        assert len(results) == 1
        assert results[0].text == "hello world"
        call_kwargs = client.iter_messages.call_args[1]
        assert call_kwargs["from_user"] == alice
        assert call_kwargs["limit"] is None

    async def test_read_from_bare_username_resolves_entity(self, client):
        user = _mock_entity("Takeshi", username="takeshi55555", id=55555)
        client.get_entity = AsyncMock(return_value=user)
        client.iter_messages = MagicMock(return_value=_async_iter([]))

        await read_messages(client, "Group", from_="takeshi55555")

        client.get_entity.assert_awaited_once_with("takeshi55555")
        call_kwargs = client.iter_messages.call_args[1]
        assert call_kwargs["from_user"] == user

    async def test_read_from_display_name_searches_chat_participants(self, client):
        user = _mock_entity("Takeshi", username="takeshi55555", id=55555)
        client.iter_participants = MagicMock(return_value=_async_iter([user]))
        client.iter_messages = MagicMock(return_value=_async_iter([]))

        await read_messages(client, "Group", from_="Takeshi")

        client.iter_participants.assert_called_once()
        call_kwargs = client.iter_messages.call_args[1]
        assert call_kwargs["from_user"] == user

    async def test_read_from_ambiguous_display_name_raises(self, client):
        users = [
            _mock_entity("Takeshi", username="takeshi1", id=1),
            _mock_entity("Takeshi", username="takeshi2", id=2),
        ]
        client.iter_participants = MagicMock(return_value=_async_iter(users))
        client.iter_messages = MagicMock(return_value=_async_iter([]))

        with pytest.raises(ValueError, match="multiple senders"):
            await read_messages(client, "Group", from_="Takeshi")

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
        c.get_entity = AsyncMock(side_effect=ValueError("not found"))
        c.iter_participants = MagicMock(return_value=_async_iter([]))
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
