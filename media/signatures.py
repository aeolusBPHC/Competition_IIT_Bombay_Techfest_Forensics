"""
Content-based file-type detection.

Media is identified by its magic bytes, never by its extension, so renamed
or extension-less files are still found. A mismatch between content and
extension is reported, because renaming is itself forensically relevant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HEADER_BYTES = 64


@dataclass(frozen=True)
class FileType:
    kind: str          # "image", "video", "telemetry" or "other"
    format: str        # e.g. "JPEG", "MP4", "SRT"
    mime: str
    extensions: tuple[str, ...]


JPEG = FileType("image", "JPEG", "image/jpeg", (".jpg", ".jpeg", ".jpe"))
PNG = FileType("image", "PNG", "image/png", (".png",))
TIFF = FileType("image", "TIFF/DNG", "image/tiff", (".tif", ".tiff", ".dng"))
HEIC = FileType("image", "HEIF", "image/heic", (".heic", ".heif"))
MP4 = FileType("video", "MP4", "video/mp4", (".mp4", ".m4v", ".lrf"))
MOV = FileType("video", "QuickTime", "video/quicktime", (".mov", ".mp4"))
AVI = FileType("video", "AVI", "video/x-msvideo", (".avi",))
SRT = FileType("telemetry", "SRT", "application/x-subrip", (".srt",))

_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1", b"avif"}
_QT_BRANDS = {b"qt  "}
_SRT_TIMECODE = re.compile(rb"\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}")
# DJI "mavic_2_style" SRT files have no timecode lines, only this pattern
_SRT_DJI_BLOCK = re.compile(rb"^\s*1\s*\r?\n\s*\d{4}[.-]\d{1,2}[.-]\d{1,2} \d{1,2}:\d{2}:\d{2}", re.M)


def detect(header: bytes, text_probe: bytes | None = None) -> FileType | None:
    """Identify a media file from its first bytes (and a text probe for SRT)."""
    if header.startswith(b"\xff\xd8\xff"):
        return JPEG
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if header[:4] in (b"II*\x00", b"MM\x00*"):
        return TIFF
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12]
        if brand in _HEIF_BRANDS:
            return HEIC
        return MOV if brand in _QT_BRANDS else MP4
    if len(header) >= 8 and header[4:8] in (b"moov", b"mdat", b"wide", b"free", b"skip"):
        return MOV  # older QuickTime files without an ftyp box
    if header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return AVI
    probe = (text_probe or header).lstrip(b"\xef\xbb\xbf")
    if _SRT_TIMECODE.search(probe[:4096]) or _SRT_DJI_BLOCK.search(probe[:4096]):
        return SRT
    return None


def extension_matches(filetype: FileType, filename: str) -> bool:
    name = filename.lower()
    return any(name.endswith(ext) for ext in filetype.extensions)


def looks_like_disk_image(header512: bytes) -> bool:
    """
    True for a raw (dd) image of a partitioned or FAT/exFAT/NTFS volume:
    an MBR/boot-sector signature 0x55AA at offset 510, or a GPT header.
    """
    if len(header512) < 512:
        return False
    if header512[510:512] == b"\x55\xaa":
        return True
    return header512[512:520] == b"EFI PART" if len(header512) >= 520 else False
