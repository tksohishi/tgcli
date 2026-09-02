from __future__ import annotations

import mimetypes
import unicodedata
from pathlib import PurePosixPath, PureWindowsPath

DEFAULT_MAX_BYTES = 100 * 1024 * 1024

# Extensions tgcli is willing to save. Anything runnable (exe, scripts,
# installers, shortcuts) and anything with active content (svg, html) is
# deliberately absent.
SAFE_EXTENSIONS = frozenset(
    {
        # images
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp",
        ".tif", ".tiff", ".avif",
        # video / audio
        ".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".mp3", ".m4a",
        ".ogg", ".oga", ".opus", ".wav", ".flac", ".aac",
        # documents
        ".pdf", ".txt", ".md", ".rtf", ".csv", ".tsv", ".json",
        ".yaml", ".yml", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".odt", ".ods", ".odp", ".epub",
    }
)  # fmt: skip

# Containers can hold anything, so they are opt-in via --allow-archives.
ARCHIVE_EXTENSIONS = frozenset(
    {".zip", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".rar"}
)

# Zip-based document formats and the member that proves they are one.
_ZIP_DOCUMENT_MARKERS = {
    ".docx": "[Content_Types].xml",
    ".xlsx": "[Content_Types].xml",
    ".pptx": "[Content_Types].xml",
    ".odt": "mimetype",
    ".ods": "mimetype",
    ".odp": "mimetype",
    ".epub": "mimetype",
}

# Legacy Office files share the compound-file header with MSI installers.
_COMPOUND_FILE_EXTENSIONS = frozenset({".doc", ".xls", ".ppt"})

EXECUTABLE_MIME_TYPES = frozenset(
    {
        "application/x-msdownload",
        "application/x-dosexec",
        "application/x-msdos-program",
        "application/vnd.microsoft.portable-executable",
        "application/x-executable",
        "application/x-sharedlib",
        "application/x-mach-binary",
        "application/x-elf",
        "application/x-msi",
        "application/x-ms-shortcut",
        "application/x-sh",
        "application/x-shellscript",
        "application/x-bat",
        "application/x-csh",
        "application/x-perl",
        "application/x-python",
        "application/x-python-code",
        "application/x-ruby",
        "application/java-archive",
        "application/vnd.android.package-archive",
        "application/x-apple-diskimage",
        "application/vnd.apple.installer+xml",
        "application/x-ms-application",
        "application/x-iso9660-image",
        "application/hta",
        "text/javascript",
        "application/javascript",
        "application/x-javascript",
        "text/x-python",
        "text/x-sh",
        "text/x-shellscript",
        "text/html",
    }
)

# Telegram-generated media has no filename; map its mime to an extension.
_MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "video/mp4": ".mp4",
}

_EXECUTABLE_MAGICS: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "Windows executable"),
    (b"ZM", "Windows executable"),
    (b"\x7fELF", "ELF executable"),
    (b"\xfe\xed\xfa\xce", "Mach-O executable"),
    (b"\xce\xfa\xed\xfe", "Mach-O executable"),
    (b"\xfe\xed\xfa\xcf", "Mach-O executable"),
    (b"\xcf\xfa\xed\xfe", "Mach-O executable"),
    (b"\xca\xfe\xba\xbe", "Mach-O universal binary or Java class"),
    (b"\xbe\xba\xfe\xca", "Mach-O universal binary"),
    (b"#!", "script with shebang"),
    (b"L\x00\x00\x00\x01\x14\x02\x00", "Windows shortcut"),
    (b"xar!", "macOS installer package"),
    (b"MSCF", "Windows cabinet"),
)

_ARCHIVE_MAGICS: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),
    (b"PK\x07\x08", "zip"),
    (b"Rar!\x1a\x07", "rar"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
)

_COMPOUND_FILE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

HEAD_SIZE = 512  # enough to cover the tar "ustar" marker at offset 257
TAIL_SIZE = 512  # DMG trailer ("koly") lives in the last 512 bytes
ISO_MARKER_OFFSET = 0x8001  # "CD001" in the primary volume descriptor

_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def target_filename(
    media_type: str, message_id: int, filename: str | None, mime_type: str | None
) -> str:
    """Pick the name tgcli will save under.

    Sender-supplied names are reduced to a basename with no control
    characters, trailing dots, or Windows reserved stems, then prefixed
    with the message id so a sender can never choose the exact name (no
    planting CLAUDE.md or package.json in an agent's cwd). Media without a
    name gets <media_type>_<message_id> plus an extension derived from the
    mime type (photos are always jpeg).
    """
    if filename:
        name = PureWindowsPath(PurePosixPath(filename).name).name
        name = "".join(
            c for c in name if unicodedata.category(c) not in {"Cc", "Cf"}
        ).strip(" .")
        if name and PurePosixPath(name).stem.upper() not in _WINDOWS_RESERVED:
            return f"{message_id}_{name}"

    if media_type == "photo":
        ext = ".jpg"
    elif mime_type:
        ext = _MIME_EXTENSIONS.get(mime_type.lower()) or (
            mimetypes.guess_extension(mime_type.lower()) or ""
        )
    else:
        ext = ""
    return f"{media_type}_{message_id}{ext}"


def reject_reason(
    filename: str, mime_type: str | None, *, allow_archives: bool = False
) -> str | None:
    """Return why an attachment must not be downloaded, or None if allowed.

    Runs before the transfer, on the name tgcli will save under.
    """
    if mime_type and mime_type.lower() in EXECUTABLE_MIME_TYPES:
        return f"executable mime type {mime_type}"

    suffix = PurePosixPath(filename).suffix.lower()
    if not suffix:
        return "file has no recognizable extension"
    if suffix in ARCHIVE_EXTENSIONS:
        if allow_archives:
            return None
        return f"archive {suffix} needs --allow-archives"
    if suffix not in SAFE_EXTENSIONS:
        return f"file type {suffix} is not allowed"
    return None


def executable_kind(header: bytes) -> str | None:
    """Return a description if the leading bytes look like an executable."""
    for magic, kind in _EXECUTABLE_MAGICS:
        if header.startswith(magic):
            return kind
    return None


def archive_kind(header: bytes) -> str | None:
    for magic, kind in _ARCHIVE_MAGICS:
        if header.startswith(magic):
            return kind
    if header[257:262] == b"ustar":
        return "tar"
    return None


def content_reject_reason(
    filename: str,
    *,
    head: bytes,
    tail: bytes,
    iso_marker: bytes,
    zip_members: list[str] | None,
    allow_archives: bool = False,
) -> str | None:
    """Return why downloaded bytes must not be kept, or None if allowed.

    Runs after the transfer, on the staged file. zip_members is the member
    list when the file is a zip (None otherwise, or if it failed to parse).
    """
    kind = executable_kind(head)
    if kind:
        return f"content is a {kind}"
    if tail.startswith(b"koly"):
        return "content is an Apple disk image"
    if iso_marker == b"CD001":
        return "content is an ISO image"

    suffix = PurePosixPath(filename).suffix.lower()

    if head.startswith(_COMPOUND_FILE_MAGIC):
        if suffix in _COMPOUND_FILE_EXTENSIONS:
            return None
        return f"content is a compound file (MSI or legacy Office) named {suffix}"

    archive = archive_kind(head)
    if archive is None:
        return None
    if archive == "zip" and suffix in _ZIP_DOCUMENT_MARKERS:
        marker = _ZIP_DOCUMENT_MARKERS[suffix]
        if zip_members is not None and marker in zip_members:
            return None
        return f"content is a zip that is not a real {suffix} document"
    if suffix in ARCHIVE_EXTENSIONS:
        if allow_archives:
            return None
        return f"archive {suffix} needs --allow-archives"
    return f"content is a {archive} archive named {suffix}"
