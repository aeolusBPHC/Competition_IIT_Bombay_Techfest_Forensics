"""
Platform-independent media extraction for drone evidence.

Input can be:
  * a directory (e.g. a mounted, write-blocked SD card or an extraction),
  * a single file, or
  * a raw disk image (dd) - files are recovered with The Sleuth Kit,
    both allocated and deleted-but-recoverable.

Media is found by content signature, never by extension or vendor. Every
file is SHA-256 hashed; images, videos and SRT telemetry are parsed with
vendor-neutral readers; each normalized value keeps the tag it came from.
If no media is present, the result says so explicitly.

    python -m media.extractor --input <dir|file|image.dd> --output report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from media import exif as exif_reader
from media import signatures, srt, video, xmp
from media.normalize import normalize

SCHEMA_VERSION = "1.0"
XMP_SCAN_BYTES = 4 * 1024 * 1024  # XMP sits in the first segments of images


@dataclass
class MediaItem:
    path: str                      # path inside the evidence
    origin: str                    # directory | file | image_allocated | image_deleted
    size_bytes: int
    sha256: str
    kind: str                      # image | video | telemetry
    format: str
    mime: str
    extension_matches_content: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    telemetry: dict[str, Any] | None = None
    sidecar_of: str | None = None
    sidecars: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def sha256_file(path: str, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _read_head(path: str, n: int) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(n)


class MediaExtractor:
    def __init__(self, input_path: str | Path, srt_gps_axis_order: str | None = None,
                 keep_recovered: str | None = None):
        """
        srt_gps_axis_order: examiner override ('lon_lat'/'lat_lon') for SRT files
            whose positional GPS order cannot be proven from the values.
        keep_recovered: directory to keep files recovered from a disk image
            (default: a temporary directory that is deleted afterwards).
        """
        self.input_path = str(input_path)
        self.srt_gps_axis_order = srt_gps_axis_order
        self.keep_recovered = keep_recovered
        self.warnings: list[str] = []
        self.input_type: str | None = None

    # ----------------------------------------------------------- contract
    @classmethod
    def identify(cls, path: str | Path) -> dict[str, Any]:
        """Cheap check in the same shape as the platform parsers' identify()."""
        path = str(path)
        result = {"supported": False, "platform": "Media", "format": None,
                  "confidence": "NONE", "reason": "", "indicators": {}}
        if os.path.isdir(path):
            found = sum(1 for p, _ in cls._walk_dir(path, limit=1))
            result.update(supported=found > 0, format="directory",
                          confidence="HIGH" if found else "NONE",
                          reason="Media files found by content signature" if found
                          else "No media files found in directory")
            return result
        try:
            head = _read_head(path, 4096)
        except OSError as exc:
            result["reason"] = f"Could not read input: {exc}"
            return result
        ftype = signatures.detect(head[:signatures.HEADER_BYTES], head)
        if ftype:
            result.update(supported=True, format=ftype.format, confidence="HIGH",
                          reason=f"{ftype.format} signature detected")
        elif signatures.looks_like_disk_image(head):
            result.update(supported=True, format="disk_image", confidence="MEDIUM",
                          reason="Boot-sector signature found; media presence is only known after "
                                 "file-system recovery")
        else:
            result["reason"] = "No media signature and not a recognizable disk image"
        return result

    # ------------------------------------------------------------ sources
    @staticmethod
    def _walk_dir(root: str, limit: int | None = None) -> Iterable[tuple[str, signatures.FileType]]:
        count = 0
        for dirpath, _, files in os.walk(root):
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                try:
                    head = _read_head(full, 4096)
                except OSError:
                    continue
                ftype = signatures.detect(head[:signatures.HEADER_BYTES], head)
                if ftype:
                    yield full, ftype
                    count += 1
                    if limit and count >= limit:
                        return

    def _recover_from_image(self, image: str, workdir: str) -> list[tuple[str, str, str]]:
        """Return (host_path, evidence_path, origin) for every recovered file."""
        if not shutil.which("tsk_recover") or not shutil.which("mmls"):
            self.warnings.append("Disk image given but The Sleuth Kit (tsk_recover, mmls) is not "
                                 "installed; install 'sleuthkit' to extract files from images")
            return []
        offsets = self._partition_offsets(image)
        out: list[tuple[str, str, str]] = []
        for off in offsets:
            alloc_dir = os.path.join(workdir, f"p{off}_allocated")
            all_dir = os.path.join(workdir, f"p{off}_all")
            for mode, target in (("-a", alloc_dir), ("-e", all_dir)):
                os.makedirs(target, exist_ok=True)
                proc = subprocess.run(["tsk_recover", mode, "-o", str(off), image, target],
                                      capture_output=True, text=True)
                if proc.returncode != 0:
                    self.warnings.append(f"tsk_recover {mode} at sector {off} failed: "
                                         f"{proc.stderr.strip()[:200]}")
            allocated = {os.path.relpath(os.path.join(d, f), alloc_dir)
                         for d, _, fs in os.walk(alloc_dir) for f in fs}
            for d, _, fs in os.walk(all_dir):
                for f in fs:
                    rel = os.path.relpath(os.path.join(d, f), all_dir)
                    origin = "image_allocated" if rel in allocated else "image_deleted"
                    out.append((os.path.join(d, f), f"partition@{off}/{rel}", origin))
        return out

    def _partition_offsets(self, image: str) -> list[int]:
        proc = subprocess.run(["mmls", image], capture_output=True, text=True)
        offsets = []
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                parts = line.split()
                if (len(parts) >= 6 and parts[0].rstrip(":").isdigit()
                        and not any(w in line for w in ("Unallocated", "Primary Table", "Safety"))
                        and "----" not in parts[1]):
                    try:
                        offsets.append(int(parts[2]))
                    except ValueError:
                        pass
        return offsets or [0]  # no partition table: file system starts at sector 0

    # ------------------------------------------------------------ parsing
    def _parse(self, host_path: str, evidence_path: str, origin: str,
               ftype: signatures.FileType) -> MediaItem:
        item = MediaItem(path=evidence_path, origin=origin, size_bytes=os.path.getsize(host_path),
                         sha256=sha256_file(host_path), kind=ftype.kind, format=ftype.format,
                         mime=ftype.mime,
                         extension_matches_content=signatures.extension_matches(ftype, evidence_path))
        if origin == "image_deleted":
            item.errors.append("recovered deleted file: content may be partly overwritten")
        try:
            if ftype.kind == "image":
                ex = exif_reader.read(host_path)
                props = xmp.extract(_read_head(host_path, XMP_SCAN_BYTES))
                item.metadata = normalize(ex, props)
                item.metadata["raw"] = {"exif": ex.get("tags", {}), "gps": ex.get("gps_raw", {}),
                                        "xmp": {p.qualified: p.value for p in props},
                                        "pixel_size": ex.get("pixel_size")}
                item.errors.extend(ex.get("errors", []))
            elif ftype.kind == "video":
                vid = video.read(host_path) if ftype.format in ("MP4", "QuickTime") else {}
                props = xmp.extract(_read_head(host_path, XMP_SCAN_BYTES))
                item.metadata = normalize(None, props, vid)
                item.metadata["raw"] = {"container": {k: v for k, v in vid.items() if k != "errors"},
                                        "xmp": {p.qualified: p.value for p in props}}
                item.errors.extend(vid.get("errors", []))
            elif ftype.kind == "telemetry":
                parsed = srt.parse_file(host_path, self.srt_gps_axis_order)
                item.telemetry = {"summary": srt.summarize(parsed),
                                  "frames": [asdict(f) for f in parsed.frames]}
        except Exception as exc:  # one bad file must never stop the case
            item.errors.append(f"parse failed: {type(exc).__name__}: {exc}")
        return item

    @staticmethod
    def _link_sidecars(items: list[MediaItem]) -> None:
        videos = {os.path.splitext(i.path)[0].lower(): i for i in items if i.kind == "video"}
        for i in items:
            if i.kind == "telemetry":
                v = videos.get(os.path.splitext(i.path)[0].lower())
                if v:
                    i.sidecar_of = v.path
                    v.sidecars.append(i.path)

    # ---------------------------------------------------------------- run
    def extract(self) -> dict[str, Any]:
        started = datetime.now(timezone.utc).isoformat()
        items: list[MediaItem] = []
        candidates: list[tuple[str, str, str]] = []
        tmp = None
        if os.path.isdir(self.input_path):
            self.input_type = "directory"
            candidates = [(p, os.path.relpath(p, self.input_path), "directory")
                          for p, _ in self._walk_dir(self.input_path)]
        else:
            head = _read_head(self.input_path, 4096)
            if signatures.detect(head[:signatures.HEADER_BYTES], head):
                self.input_type = "file"
                candidates = [(self.input_path, os.path.basename(self.input_path), "file")]
            elif signatures.looks_like_disk_image(head):
                self.input_type = "disk_image"
                tmp = self.keep_recovered or tempfile.mkdtemp(prefix="media_recover_")
                os.makedirs(tmp, exist_ok=True)
                candidates = self._recover_from_image(self.input_path, tmp)
            else:
                self.input_type = "unrecognized"
                self.warnings.append("input is neither media nor a recognizable disk image")
        try:
            for host, evid, origin in candidates:
                try:
                    head = _read_head(host, 4096)
                except OSError:
                    continue
                ftype = signatures.detect(head[:signatures.HEADER_BYTES], head)
                if ftype:
                    items.append(self._parse(host, evid, origin, ftype))
        finally:
            if tmp and not self.keep_recovered:
                shutil.rmtree(tmp, ignore_errors=True)
        self._link_sidecars(items)
        return self._report(items, started)

    def _report(self, items: list[MediaItem], started: str) -> dict[str, Any]:
        input_hash = sha256_file(self.input_path) if os.path.isfile(self.input_path) else None
        counts: dict[str, int] = {}
        for i in items:
            counts[i.kind] = counts.get(i.kind, 0) + 1
        makes = sorted({str(i.metadata.get("fields", {}).get("make", {}).get("value"))
                        for i in items if i.metadata.get("fields", {}).get("make")})
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_utc": started,
            "input": {"path": self.input_path, "type": self.input_type, "sha256": input_hash},
            "media_present": bool(items),
            "summary": {
                "media_count": len(items),
                "by_kind": counts,
                "deleted_recovered": sum(1 for i in items if i.origin == "image_deleted"),
                "extension_mismatches": sum(1 for i in items if not i.extension_matches_content),
                "with_position": sum(1 for i in items if "latitude" in i.metadata.get("fields", {})),
                "with_drone_telemetry": sum(1 for i in items if i.metadata.get("drone_telemetry_present")),
                "flagged": sum(1 for i in items if i.metadata.get("flags")),
                "makes": makes,
            },
            "warnings": self.warnings,
            "items": [asdict(i) for i in items],
        }


# ------------------------------------------------------- normalized records
def to_gps_records(report: dict[str, Any]) -> tuple[list, int]:
    """
    Convert positions into the toolkit's GPSRecord type (photos and SRT frames).

    Timestamps: photos use GPS UTC when recorded; SRT frames carry only the
    drone's device clock, so their records use the video-relative time
    (start_s) and keep the device time in raw. Photos with a position but no
    GPS UTC time are NOT converted (a camera clock is not a reliable time
    base); they are counted in the second return value and remain in the
    media report.
    """
    from platform_parsers.common.evidence_model import GPSRecord

    records = []
    skipped_no_time = 0
    for item in report["items"]:
        f = item.get("metadata", {}).get("fields", {})
        if "latitude" in f and "longitude" in f:
            utc = f.get("gps_utc_time", {}).get("value")
            ts = None
            if utc:
                try:
                    parsed = datetime.fromisoformat(utc.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:  # the field is UTC by definition
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    ts = parsed.timestamp()
                except ValueError:
                    ts = None
            if ts is None:
                skipped_no_time += 1
            else:
                records.append(GPSRecord(
                timestamp=ts,
                latitude=f["latitude"]["value"], longitude=f["longitude"]["value"],
                altitude_m=f.get("gps_altitude_m", {}).get("value"),
                heading_deg=f.get("image_direction_deg", {}).get("value"),
                source_platform=f"Media:{f.get('make', {}).get('value', 'unknown')}",
                raw={"media_path": item["path"], "sha256": item["sha256"],
                     "timestamp_basis": "gps_utc",
                     "sources": {k: v["source"] for k, v in f.items()}},
                ))
        tel = item.get("telemetry")
        if tel:
            for fr in tel["frames"]:
                if fr["latitude"] is None:
                    continue
                records.append(GPSRecord(
                    timestamp=fr["start_s"] if fr["start_s"] is not None else float(fr["index"]),
                    latitude=fr["latitude"], longitude=fr["longitude"],
                    altitude_m=fr["absolute_altitude_m"] if fr["absolute_altitude_m"] is not None else fr["altitude_m"],
                    speed_m_s=fr["horizontal_speed_m_s"],
                    source_platform="Media:SRT",
                    raw={"media_path": item["path"], "sha256": item["sha256"], "frame": fr["index"],
                         "device_time": fr["device_time"],
                         "timestamp_basis": "video_relative_s" if fr["start_s"] is not None else "frame_index",
                         "gps_axis_order": tel["summary"]["gps_axis_order"]},
                ))
    return records, skipped_no_time


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Platform-independent drone media extraction")
    ap.add_argument("--input", required=True, help="directory, media file or raw disk image")
    ap.add_argument("--output", required=True, help="JSON report path (a .sha256 sidecar is written)")
    ap.add_argument("--srt-gps-axis-order", choices=["lon_lat", "lat_lon"],
                    help="examiner override for SRT files whose GPS order cannot be proven")
    ap.add_argument("--keep-recovered", help="keep files recovered from a disk image here")
    args = ap.parse_args(argv)

    ident = MediaExtractor.identify(args.input)
    print(f"[identify] {ident['format']} | supported={ident['supported']} | {ident['reason']}")
    report = MediaExtractor(args.input, args.srt_gps_axis_order, args.keep_recovered).extract()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, default=str)
    digest = sha256_file(args.output)
    Path(args.output + ".sha256").write_text(f"{digest}  {os.path.basename(args.output)}\n")

    s = report["summary"]
    print(f"[input]   {report['input']['type']} sha256={report['input']['sha256']}")
    if not report["media_present"]:
        print("[result]  NO MEDIA PRESENT")
    else:
        print(f"[result]  {s['media_count']} media files {s['by_kind']} | deleted recovered: "
              f"{s['deleted_recovered']} | with position: {s['with_position']} | drone telemetry: "
              f"{s['with_drone_telemetry']} | flagged: {s['flagged']} | extension mismatches: "
              f"{s['extension_mismatches']}")
        print(f"[makes]   {', '.join(s['makes']) or 'none recorded'}")
    for w in report["warnings"]:
        print(f"[warning] {w}")
    print(f"[report]  {args.output}\n[sha256]  {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
