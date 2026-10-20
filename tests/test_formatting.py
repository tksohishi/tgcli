from __future__ import annotations

import base64
import json
from io import StringIO

import pytest
import qrcode
from rich.console import Console

from tgcli.formatting import (
    ChatData,
    format_auth_status,
    format_chat_jsonl,
    format_context,
    format_message_jsonl,
    format_qr,
    format_search_results,
)


def _render(renderable) -> str:
    buf = StringIO()
    Console(file=buf, width=120, force_terminal=True).print(renderable)
    return buf.getvalue()


class TestFormatChatJsonl:
    def test_includes_numeric_entity_id(self):
        chat = ChatData(
            id=123,
            name="Mira Vale | Example",
            chat_type="user",
            unread_count=0,
            pinned=False,
            date=None,
        )

        assert json.loads(format_chat_jsonl(chat)) == {
            "id": 123,
            "name": "Mira Vale | Example",
            "chat_type": "user",
            "unread_count": 0,
            "pinned": False,
            "date": None,
        }


class TestFormatMessageJsonl:
    def test_basic_serialization(self, make_message):
        msg = make_message(
            id=1,
            text="hello",
            chat_name="Group",
            sender_name="Bob",
            sender_username="bob_handle",
            sender_id=42,
        )
        line = format_message_jsonl(msg)
        d = json.loads(line)

        assert d["id"] == 1
        assert d["text"] == "hello"
        assert d["chat_name"] == "Group"
        assert d["sender_name"] == "Bob"
        assert d["sender_username"] == "bob_handle"
        assert d["sender_id"] == 42
        assert d["date"] == "2025-06-15T12:00:00+00:00"
        assert "target" not in d

    def test_nullable_sender_username(self, make_message):
        msg = make_message(sender_username=None, sender_id=42)
        line = format_message_jsonl(msg)
        d = json.loads(line)

        assert d["sender_username"] is None
        assert d["sender_id"] == 42

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
        assert "stored locally" in output

    def test_authenticated_keychain(self):
        output = _render(
            format_auth_status(
                authenticated=True,
                session_exists=True,
                session_store="keychain",
            )
        )

        assert "stored in keychain" in output

    def test_not_authenticated(self):
        output = _render(format_auth_status(authenticated=False, session_exists=False))

        assert "not authenticated" in output
        assert "none (file)" in output


def _token_url(nbytes: int) -> str:
    token = base64.urlsafe_b64encode(bytes(range(nbytes))).decode().rstrip("=")
    return f"tg://login?token={token}"


class TestFormatQr:
    # Each glyph carries two vertically stacked modules.
    UNMAP = {"\u2588": (True, True), "\u2580": (True, False),
             "\u2584": (False, True), " ": (False, False)}  # fmt: skip

    def test_round_trips_the_module_matrix(self):
        """The half-block packing must be lossless, or the code will not scan."""
        url = _token_url(24)
        reference = qrcode.QRCode(
            border=2, error_correction=qrcode.constants.ERROR_CORRECT_L
        )
        reference.add_data(url)
        reference.make(fit=True)
        expected = [[bool(cell) for cell in row] for row in reference.get_matrix()]

        rows: list[list[bool]] = []
        for line in format_qr(url).plain.split("\n"):
            pairs = [self.UNMAP[char] for char in line]
            rows.append([top for top, _ in pairs])
            rows.append([bottom for _, bottom in pairs])

        # An odd-height matrix is padded with one all-light row at the bottom.
        assert rows[len(expected) :] in ([], [[False] * len(expected[0])])
        assert rows[: len(expected)] == expected

    def test_uses_only_half_block_glyphs(self):
        assert set(format_qr(_token_url(24)).plain) <= set(self.UNMAP) | {"\n"}

    def test_pins_black_on_white(self):
        """Scanners need dark modules on a light field, whatever the theme."""
        assert format_qr(_token_url(24)).style == "black on white"

    def test_rows_are_equal_width(self):
        lines = format_qr(_token_url(24)).plain.split("\n")

        assert len({len(line) for line in lines}) == 1

    def test_keeps_a_quiet_zone_around_the_code(self):
        lines = format_qr(_token_url(24)).plain.split("\n")

        assert lines[0].strip() == ""
        assert lines[-1].strip() == ""
        assert all(line.startswith("  ") and line.endswith("  ") for line in lines)

    @pytest.mark.parametrize("nbytes", [16, 24, 32, 40])
    def test_fits_a_standard_terminal(self, nbytes):
        lines = format_qr(_token_url(nbytes)).plain.split("\n")

        assert len(lines) <= 21
        assert len(lines[0]) <= 45

    def test_renders_through_a_console(self):
        output = _render(format_qr(_token_url(24)))

        assert "\u2588" in output
