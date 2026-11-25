"""Read-only removable-media filesystem timeline using The Sleuth Kit."""

from __future__ import annotations

import shutil
import subprocess
import re
from datetime import datetime, timezone
from typing import Any


TIMESTAMP_LABELS = {
    "accessed": (
        "Filesystem access time (atime). It may be disabled, stale, or changed "
        "by later access; it is not a creation time."
    ),
    "modified": (
        "Filesystem content-modification time (mtime). Clock setting, timezone "
        "handling, and filesystem resolution may be unknown."
    ),
    "metadata_changed": (
        "Filesystem metadata-change time (ctime). This is not a creation time; "
        "its exact semantics vary by filesystem."
    ),
    "filesystem_created": (
        "Filesystem creation/birth time (crtime) when recorded. Filesystem "
        "support, clock setting, timezone handling, and timestamp resolution "
        "may be unknown; it does not establish absolute creation or acquisition time."
    ),
}


def _timestamp(raw: str, name: str) -> dict[str, Any] | None:
    if raw in ("", "-", "0"):
        return None
    try:
        epoch = int(raw)
        utc = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None
    return {
        "epoch_s": epoch,
        "utc": utc,
        "source_field": {"accessed": "atime", "modified": "mtime",
                         "metadata_changed": "ctime", "filesystem_created": "crtime"}[name],
        "meaning_and_limits": TIMESTAMP_LABELS[name],
    }


def filesystem_timestamp_limits(fs_type: str | None) -> list[str]:
    name = (fs_type or "").lower()
    limits = []
    if "fat" in name and "exfat" not in name:
        limits.append("FAT timestamps have field-specific coarse precision: modification time is typically 2 seconds, access time is date-only, and creation time has a fractional field; timezone interpretation is device/tool dependent.")
    elif "exfat" in name:
        limits.append("exFAT timestamp fractions may encode 10 ms increments; local-offset fields and tool normalization affect UTC interpretation.")
    elif "ntfs" in name:
        limits.append("NTFS stores high-resolution timestamps, but bodyfile output may omit alternate $FILE_NAME timestamps and does not establish the device clock or event meaning.")
    else:
        limits.append("Filesystem-specific timestamp resolution and semantics were not established for this volume.")
    return limits


def parse_bodyfile(bodyfile: str, partition_offset_sectors: int,
                   filesystem_type: str | None = None) -> list[dict[str, Any]]:
    """Parse TSK fls -m bodyfile lines into file records and ordered events."""
    records = []
    for line in bodyfile.splitlines():
        parts = line.split("|", 10)
        if len(parts) < 11:
            continue
        _, raw_name, meta_address, mode, uid, gid, size, atime, mtime, ctime, crtime = parts
        raw_name = raw_name.strip()
        cleaned_name = raw_name.lstrip("* ")
        deleted_marker = re.search(r"\s+\(deleted(?:-[^)]+)?\)$", cleaned_name, re.IGNORECASE)
        deleted = raw_name.startswith("*") or deleted_marker is not None
        reallocated = deleted_marker is not None and "realloc" in deleted_marker.group(0).lower()
        path = cleaned_name[:deleted_marker.start()] if deleted_marker else cleaned_name
        timestamps = {
            "accessed": _timestamp(atime, "accessed"),
            "modified": _timestamp(mtime, "modified"),
            "metadata_changed": _timestamp(ctime, "metadata_changed"),
            "filesystem_created": _timestamp(crtime, "filesystem_created"),
        }
        try:
            size_bytes = int(size)
        except ValueError:
            size_bytes = None
        record = {
            "path": path,
            "raw_name": raw_name,
            "status": ("deleted_entry_reallocated" if reallocated else "deleted_entry")
                      if deleted else "allocated_entry",
            "metadata_address": meta_address,
            "mode": mode,
            "uid": uid,
            "gid": gid,
            "size_bytes": size_bytes,
            "partition_offset_sectors": partition_offset_sectors,
            "filesystem_type": filesystem_type,
            "timestamps": timestamps,
            "deletion_time": None,
            "deletion_note": (
                "A deleted directory entry was reported by fls; the entry does "
                "not provide a defensible deletion timestamp. Its content may "
                "be incomplete or overwritten."
                if deleted else None
            ),
        }
        records.append(record)
    return records


def build_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = []
    for record in records:
        for event_type, timestamp in (record.get("timestamps") or {}).items():
            if timestamp:
                events.append({
                    "time_epoch_s": timestamp["epoch_s"],
                    "time_utc": timestamp["utc"],
                    "timestamp_type": event_type,
                    "timestamp_source_field": timestamp["source_field"],
                    "path": record["path"],
                    "filesystem_type": record.get("filesystem_type"),
                    "entry_status": record["status"],
                    "partition_offset_sectors": record["partition_offset_sectors"],
                    "meaning_and_limits": timestamp["meaning_and_limits"],
                })
    return sorted(events, key=lambda event: (
        event["time_epoch_s"], event["path"], event["timestamp_type"]
    ))


def extract(image_path: str, partition_offsets: list[int], *, timeout_s: int = 180) -> dict[str, Any]:
    """Extract allocated/deleted filesystem entries without changing the image."""
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "unavailable",
        "source": "The Sleuth Kit fls bodyfile",
        "timestamp_basis": "UTC rendering of Sleuth Kit bodyfile epoch values; original device timezone is not established",
        "timestamp_notes": [
            "Filesystem timestamps describe filesystem metadata, not verified real-world events.",
            "Device clock, timezone, and timestamp resolution may be unknown.",
            "Access time can change when files are read; acquisition and analysis can affect some metadata.",
            "A deleted entry is not a deletion-time record; deleted contents can be incomplete or overwritten.",
            "The extractor does not set a device timezone or infer a timezone from the image.",
        ],
        "partitions": [],
        "records": [],
        "events": [],
        "summary": {"partition_count": 0, "entry_count": 0,
                    "allocated_entries": 0, "deleted_entries": 0, "event_count": 0},
        "warnings": [],
    }
    if not shutil.which("fls"):
        result["warnings"].append("The Sleuth Kit fls is not installed; filesystem timeline unavailable")
        return result

    for offset in partition_offsets or [0]:
        fs_type = None
        fsstat = shutil.which("fsstat")
        if fsstat:
            try:
                stat = subprocess.run([fsstat, "-o", str(offset), image_path],
                                      capture_output=True, text=True, encoding="utf-8",
                                      errors="replace", timeout=timeout_s, check=False)
                match = re.search(r"File System Type:\s*([^\r\n]+)", stat.stdout, re.IGNORECASE)
                fs_type = match.group(1).strip() if match else None
            except (OSError, subprocess.TimeoutExpired):
                result["warnings"].append(f"Could not identify filesystem at partition offset {offset}")
        try:
            proc = subprocess.run(
                ["fls", "-r", "-m", "/", "-o", str(offset), image_path],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout_s, check=False,
            )
        except subprocess.TimeoutExpired:
            result["warnings"].append(
                f"fls timed out after {timeout_s} seconds at partition offset {offset}"
            )
            continue
        except OSError as exc:
            result["warnings"].append(
                f"Could not run fls at partition offset {offset}: {type(exc).__name__}: {exc}"
            )
            continue
        partition = {"offset_sectors": offset, "returncode": proc.returncode,
                     "filesystem_type": fs_type,
                     "timestamp_limits": filesystem_timestamp_limits(fs_type)}
        result["partitions"].append(partition)
        if proc.returncode:
            detail = proc.stderr.strip().splitlines()
            result["warnings"].append(
                f"fls failed at partition offset {offset}"
                + (f": {detail[-1][:300]}" if detail else "")
            )
            continue
        result["records"].extend(parse_bodyfile(proc.stdout, offset, fs_type))

    result["events"] = build_events(result["records"])
    filesystem_notes = [note for partition in result["partitions"]
                        for note in partition.get("timestamp_limits", [])]
    result["timestamp_notes"] = list(dict.fromkeys(result["timestamp_notes"] + filesystem_notes))
    result["summary"].update({
        "partition_count": len(result["partitions"]),
        "entry_count": len(result["records"]),
        "allocated_entries": sum(r["status"] == "allocated_entry" for r in result["records"]),
        "deleted_entries": sum(r["status"].startswith("deleted_entry") for r in result["records"]),
        "event_count": len(result["events"]),
    })
    any_partition_succeeded = any(partition.get("returncode") == 0
                                   for partition in result["partitions"])
    result["status"] = ("ok" if result["records"] else
                        "empty" if any_partition_succeeded else "error")
    if not result["records"] and not result["warnings"]:
        result["warnings"].append("fls found no filesystem entries at the detected partition offsets")
    return result
