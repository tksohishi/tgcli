from __future__ import annotations

import asyncio
import io
import os
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telethon.tl.types import (
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
    MessageMediaContact,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
)

from tgcli.client import _media_info, download_media
from tgcli.media import (
    archive_kind,
    content_reject_reason,
    executable_kind,
    reject_reason,
    target_filename,
)

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
PDF = b"%PDF-1.7\n" + b"\x00" * 100
PE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 100


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


class TestTargetFilename:
    def test_prefixes_original_name_with_message_id(self):
        assert target_filename("document", 1, "report.pdf", None) == "1_report.pdf"
        # A sender cannot plant agent or tool config files by exact name.
        assert target_filename("document", 1, "CLAUDE.md", None) == "1_CLAUDE.md"

    def test_strips_paths_and_control_chars(self):
        assert target_filename("document", 1, "../../x/report.pdf", None) == (
            "1_report.pdf"
        )
        assert target_filename("document", 1, "C:\\Users\\x\\report.pdf", None) == (
            "1_report.pdf"
        )
        # RTL override trick: displays as "annexe exe.png", real suffix .exe
        assert target_filename("document", 1, "annexe\u202egnp.exe", None) == (
            "1_annexegnp.exe"
        )
        assert target_filename("document", 1, "report.pdf. ", None) == "1_report.pdf"

    def test_reserved_or_empty_names_fall_back(self):
        assert target_filename("document", 7, "CON.txt", "text/plain") == (
            "document_7.txt"
        )
        assert target_filename("document", 7, "...", "text/plain") == "document_7.txt"

    def test_unnamed_media_uses_mime(self):
        assert target_filename("photo", 7, None, None) == "photo_7.jpg"
        assert target_filename("voice", 7, None, "audio/ogg") == "voice_7.ogg"
        assert target_filename("video", 7, None, "video/mp4") == "video_7.mp4"
        assert target_filename("sticker", 7, None, "image/webp") == "sticker_7.webp"
        assert target_filename("document", 7, None, "application/zip") == (
            "document_7.zip"
        )
        assert target_filename("document", 7, None, None) == "document_7"


class TestRejectReason:
    @pytest.mark.parametrize(
        "filename", ["report.pdf", "photo.JPG", "clip.mp4", "notes.txt"]
    )
    def test_allows_safe_extensions(self, filename):
        assert reject_reason(filename, "application/octet-stream") is None

    @pytest.mark.parametrize(
        "filename",
        [
            "setup.exe", "invoice.pdf.exe", "run.bat", "script.sh", "app.dmg",
            "thing.apk", "open.lnk", "run.ps1", "page.html", "image.svg",
            "feed.xml", "noext", "document_7",
        ],
    )  # fmt: skip
    def test_rejects_unsafe_extensions(self, filename):
        assert reject_reason(filename, None) is not None

    @pytest.mark.parametrize("filename", ["data.zip", "backup.tar.gz", "x.7z"])
    def test_archives_are_opt_in(self, filename):
        reason = reject_reason(filename, None)
        assert reason is not None
        assert "--allow-archives" in reason
        assert reject_reason(filename, None, allow_archives=True) is None

    def test_rejects_executable_mime_even_with_safe_name(self):
        reason = reject_reason("photo.jpg", "application/x-msdownload")
        assert reason is not None
        assert "mime" in reason

    def test_unnamed_zip_still_needs_flag(self):
        name = target_filename("document", 7, None, "application/zip")
        assert "--allow-archives" in reject_reason(name, "application/zip")


class TestMagic:
    def test_detects_binaries(self):
        assert executable_kind(PE) is not None
        assert executable_kind(b"\x7fELF\x02\x01\x01\x00") is not None
        assert executable_kind(b"\xcf\xfa\xed\xfe\x07\x00\x00\x01") is not None
        assert executable_kind(b"#!/bin/sh") is not None
        assert executable_kind(b"MSCF\x00\x00\x00\x00") is not None

    def test_allows_real_media(self):
        assert executable_kind(JPEG) is None
        assert executable_kind(PDF) is None
        assert executable_kind(b"") is None

    def test_archive_kinds(self):
        assert archive_kind(b"PK\x03\x04") == "zip"
        assert archive_kind(b"\x1f\x8b\x08") == "gzip"
        assert archive_kind(b"\x00" * 257 + b"ustar") == "tar"
        assert archive_kind(JPEG) is None


class TestContentRejectReason:
    def _check(self, name, data, zip_members=None, allow_archives=False):
        return content_reject_reason(
            name,
            head=data[:512],
            tail=data[-512:],
            iso_marker=data[0x8001 : 0x8001 + 5],
            zip_members=zip_members,
            allow_archives=allow_archives,
        )

    def test_zip_renamed_as_pdf(self):
        data = _zip_bytes({"evil.exe": PE})
        assert "zip archive named .pdf" in self._check("report.pdf", data, ["evil.exe"])

    def test_jar_renamed_as_docx(self):
        assert "not a real .docx" in self._check(
            "report.docx", _zip_bytes({"META-INF/MANIFEST.MF": b""}), ["META-INF/x"]
        )

    def test_real_docx_and_epub(self):
        members = ["[Content_Types].xml", "word/document.xml"]
        assert self._check("report.docx", _zip_bytes({}), members) is None
        assert self._check("book.epub", _zip_bytes({}), ["mimetype"]) is None

    def test_zip_with_flag(self):
        data = _zip_bytes({"a.txt": b"x"})
        assert "--allow-archives" in self._check("data.zip", data, ["a.txt"])
        assert self._check("data.zip", data, ["a.txt"], allow_archives=True) is None

    def test_gzip_renamed_as_pdf(self):
        assert "gzip archive" in self._check("report.pdf", b"\x1f\x8b\x08" + PDF)

    def test_msi_under_pdf_name_but_legacy_doc_ok(self):
        cfb = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100
        assert "compound file" in self._check("report.pdf", cfb)
        assert self._check("report.doc", cfb) is None

    def test_dmg_and_iso(self):
        dmg = JPEG + b"\x00" * 1024 + b"koly" + b"\x00" * 508
        assert "disk image" in self._check("photo.jpg", dmg)
        iso = b"\x00" * 0x8001 + b"CD001" + b"\x00" * 1024
        assert "ISO image" in self._check("photo.jpg", iso)

    def test_real_media_passes(self):
        assert self._check("photo.jpg", JPEG) is None
        assert self._check("report.pdf", PDF) is None


class TestMediaInfo:
    def test_document_filename(self):
        media = MagicMock(spec=MessageMediaDocument)
        media.document = MagicMock()
        media.document.attributes = [DocumentAttributeFilename("report.pdf")]
        assert _media_info(media) == ("document", "report.pdf")

    def test_attribute_precedence_is_order_independent(self):
        media = MagicMock(spec=MessageMediaDocument)
        media.document = MagicMock()
        voice = DocumentAttributeAudio(duration=1, voice=True)
        video = DocumentAttributeVideo(duration=1, w=1, h=1)
        sticker = DocumentAttributeSticker(alt="", stickerset=None)
        media.document.attributes = [video, voice]
        assert _media_info(media)[0] == "voice"
        media.document.attributes = [voice, sticker]
        assert _media_info(media)[0] == "sticker"
        media.document.attributes = [video]
        assert _media_info(media)[0] == "video"

    def test_other_kinds(self):
        assert _media_info(MagicMock(spec=MessageMediaPhoto)) == ("photo", None)
        assert _media_info(MagicMock(spec=MessageMediaWebPage)) == ("webpage", None)
        assert _media_info(MagicMock(spec=MessageMediaContact)) == ("other", None)
        assert _media_info(None) == (None, None)


def _document_msg(filename, mime, size=10, attrs=()):
    msg = MagicMock()
    msg.media = MagicMock(spec=MessageMediaDocument)
    msg.media.document = MagicMock()
    msg.media.document.mime_type = mime
    msg.media.document.size = size
    msg.media.document.attributes = list(attrs) + (
        [DocumentAttributeFilename(filename)] if filename else []
    )
    return msg


def _photo_msg():
    msg = MagicMock()
    msg.media = MagicMock(spec=MessageMediaPhoto)
    return msg


def _client(msg, payload: bytes | None = None):
    """Fake client whose download_media writes payload into the given handle."""
    client = AsyncMock()
    client.get_messages = AsyncMock(return_value=msg)

    async def fake_download(_msg, file):
        file.write(payload)
        return file

    client.download_media = AsyncMock(side_effect=fake_download)
    return client


def _run(client, out, **kw):
    return asyncio.run(download_media(client, "Group", 10, str(out), **kw))


@patch("tgcli.client._resolve_entity", new_callable=AsyncMock)
class TestDownloadMedia:
    def test_disguised_exe_is_deleted(self, _resolve, tmp_path):
        client = _client(_document_msg("photo.jpg", "image/jpeg"), PE)
        with pytest.raises(ValueError, match="Windows executable"):
            _run(client, tmp_path)
        assert os.listdir(tmp_path) == []

    def test_refuses_exe_before_download(self, _resolve, tmp_path):
        client = _client(_document_msg("setup.exe", "application/octet-stream"))
        with pytest.raises(ValueError, match="not allowed"):
            _run(client, tmp_path)
        client.download_media.assert_not_awaited()
        assert os.listdir(tmp_path) == []

    def test_unnamed_zip_needs_flag(self, _resolve, tmp_path):
        client = _client(_document_msg(None, "application/zip"))
        with pytest.raises(ValueError, match="--allow-archives"):
            _run(client, tmp_path)
        client.download_media.assert_not_awaited()

    def test_unnamed_audio_metadata_cannot_pick_name(self, _resolve, tmp_path):
        audio = DocumentAttributeAudio(
            duration=1, voice=False, performer="run.ps1", title="x"
        )
        client = _client(
            _document_msg(None, "audio/mpeg", attrs=[audio]), b"ID3" + b"\x00" * 64
        )
        path, media_type = _run(client, tmp_path)
        assert os.path.basename(path) == "document_10.mp3"
        assert media_type == "document"

    def test_zip_renamed_pdf_is_deleted(self, _resolve, tmp_path):
        client = _client(
            _document_msg("report.pdf", "application/pdf"), _zip_bytes({"a.exe": PE})
        )
        with pytest.raises(ValueError, match="zip archive named .pdf"):
            _run(client, tmp_path)
        assert os.listdir(tmp_path) == []

    def test_real_docx_kept(self, _resolve, tmp_path):
        data = _zip_bytes({"[Content_Types].xml": b"<x/>", "word/document.xml": b""})
        client = _client(
            _document_msg(
                "report.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            data,
        )
        path, _ = _run(client, tmp_path)
        assert os.path.basename(path) == "10_report.docx"
        assert open(path, "rb").read() == data

    def test_photo_kept_under_generated_name(self, _resolve, tmp_path):
        path, media_type = _run(_client(_photo_msg(), JPEG), tmp_path)
        assert (path, media_type) == (str(tmp_path / "photo_10.jpg"), "photo")
        assert os.listdir(tmp_path) == ["photo_10.jpg"]

    def test_failed_transfer_leaves_nothing(self, _resolve, tmp_path):
        client = _client(_document_msg("report.pdf", "application/pdf"))

        async def boom(_msg, file):
            file.write(PE[:4])
            raise ConnectionError("network")

        client.download_media = AsyncMock(side_effect=boom)
        with pytest.raises(ConnectionError):
            _run(client, tmp_path)
        assert os.listdir(tmp_path) == []

    def test_never_overwrites_or_follows_symlink(self, _resolve, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        out = tmp_path / "out"
        out.mkdir()
        os.symlink(outside / "victim.pdf", out / "10_report.pdf")
        (out / "photo_10.jpg").write_bytes(b"keep me")

        client = _client(_document_msg("report.pdf", "application/pdf"), PDF)
        path, _ = _run(client, out)
        assert path == str(out / "10_report (1).pdf")
        assert not (outside / "victim.pdf").exists()
        assert open(path, "rb").read() == PDF

        path, _ = _run(_client(_photo_msg(), JPEG), out)
        assert path == str(out / "photo_10 (1).jpg")
        assert (out / "photo_10.jpg").read_bytes() == b"keep me"

    def test_transfer_is_cut_off_at_limit(self, _resolve, tmp_path):
        # Photos have no pre-check size, and a document may lie about it.
        client = _client(_photo_msg(), JPEG + b"\x00" * 5000)
        with pytest.raises(ValueError, match="exceeded"):
            _run(client, tmp_path, max_bytes=1000)
        assert os.listdir(tmp_path) == []

    def test_empty_transfer_is_no_media(self, _resolve, tmp_path):
        client = _client(_photo_msg(), b"")
        with pytest.raises(ValueError, match="no downloadable media"):
            _run(client, tmp_path)
        assert os.listdir(tmp_path) == []

    def test_dmg_and_iso_deleted_end_to_end(self, _resolve, tmp_path):
        dmg = JPEG + b"\x00" * 1024 + b"koly" + b"\x00" * 508
        with pytest.raises(ValueError, match="disk image"):
            _run(_client(_photo_msg(), dmg), tmp_path)
        iso = b"\x00" * 0x8001 + b"CD001" + b"\x00" * 1024
        with pytest.raises(ValueError, match="ISO image"):
            _run(_client(_photo_msg(), iso), tmp_path)
        assert os.listdir(tmp_path) == []

    def test_size_limit(self, _resolve, tmp_path):
        client = _client(_document_msg("big.pdf", "application/pdf", size=2_000_000))
        with pytest.raises(ValueError, match="exceeds"):
            _run(client, tmp_path, max_bytes=1_000_000)
        client.download_media.assert_not_awaited()

    def test_contact_and_webpage_are_no_media(self, _resolve, tmp_path):
        for spec in (MessageMediaWebPage, MessageMediaContact):
            msg = MagicMock()
            msg.media = MagicMock(spec=spec)
            with pytest.raises(ValueError, match="no downloadable media"):
                _run(_client(msg), tmp_path)

    def test_missing_message(self, _resolve, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            _run(_client(None), tmp_path)
