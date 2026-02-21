from __future__ import annotations

import json
from io import StringIO

from rich.console import Console

from tg_cli.formatting import (
    format_auth_status,
    format_context,
    format_message_jsonl,
    format_search_results,
)


def _render(renderable) -> str:
    buf = StringIO()
    Console(file=buf, width=120, force_terminal=True).print(renderable)
    return buf.getvalue()


class TestFormatMessageJsonl:
    def test_basic_serialization(self, make_message):
        msg = make_message(id=1, text="hello", chat_name="Group", sender_name="Bob")
        line = format_message_jsonl(msg)
        d = json.loads(line)

        assert d["id"] == 1
        assert d["text"] == "hello"
        assert d["chat_name"] == "Group"
        assert d["sender_name"] == "Bob"
        assert d["date"] == "2025-06-15T12:00:00+00:00"
        assert "target" not in d

    def test_flags_included_when_true(self, make_message):
        msg = make_message(id=2)
        line = format_message_jsonl(msg, target=True, replied_to=False)
        d = json.loads(line)

        assert d["target"] is True
        assert "replied_to" not in d

    def test_unicode(self, make_message):
        msg = make_message(text="こんにちは")
        line = format_message_jsonl(msg)
        d = json.loads(line)

        assert d["text"] == "こんにちは"


class TestFormatSearchResults:
    def test_basic_table(self, make_message):
        msgs = [
            make_message(
                id=1, text="hello world", chat_name="Group", sender_name="Bob"
            ),
            make_message(id=2, text="second msg", chat_name="DM", sender_name="Eve"),
        ]
        output = _render(format_search_results(msgs))

        assert "hello world" in output
        assert "second msg" in output
        assert "Group" in output
        assert "Bob" in output

    def test_truncation(self, make_message):
        long_text = "\n".join(f"line {i}" for i in range(10))
        msgs = [make_message(text=long_text)]
        output = _render(format_search_results(msgs))

        assert "line 0" in output
        assert "line 2" in output
        assert "..." in output
        assert "line 9" not in output

    def test_empty_list(self):
        output = _render(format_search_results([]))
        assert "Date" in output  # header still present


class TestFormatContext:
    def test_target_message_present(self, make_message):
        msgs = [
            make_message(id=1, text="before"),
            make_message(id=2, text="TARGET"),
            make_message(id=3, text="after"),
        ]
        output = _render(format_context(msgs, target_id=2))

        assert "TARGET" in output
        assert "before" in output
        assert "after" in output

    def test_replied_to_shown(self, make_message):
        target = make_message(id=2, text="my reply", reply_to_msg_id=1)
        replied = make_message(id=1, text="original message", sender_name="Bob")
        output = _render(format_context([target], target_id=2, replied_to=replied))

        assert "original message" in output
        assert ">>" in output
        assert "Bob" in output


class TestFormatAuthStatus:
    def test_authenticated(self):
        output = _render(
            format_auth_status(authenticated=True, phone="+1***99", session_exists=True)
        )

        assert "authenticated" in output
        assert "+1***99" in output
        assert "Keychain" in output

    def test_not_authenticated(self):
        output = _render(format_auth_status(authenticated=False, session_exists=False))

        assert "not authenticated" in output
        assert "none" in output
