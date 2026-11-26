"""Render media evidence from a media extractor JSON report into case HTML."""

from __future__ import annotations

import html
import hashlib
import json
import mimetypes
import os
import shutil
from pathlib import Path
from urllib.parse import quote
from typing import Any


def find_media_report(candidates: list[Path]) -> tuple[dict[str, Any] | None, Path | None]:
    """Load the first existing media report in candidate order."""
    seen = set()
    for candidate in candidates:
        try:
            path = candidate.expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            return value, path
    return None, None


def _resolve_media_path(media_report: dict[str, Any], report_path: Path,
                        item_path: str) -> Path | None:
    # Disk-image evidence paths preserve partition identity, not host paths.
    recovered = media_report.get("recovered_root")
    if recovered and item_path.startswith("partition@"):
        partition, _, relative = item_path.partition("/")
        offset = partition.removeprefix("partition@")
        root = (Path(recovered) / f"p{offset}_all").resolve()
        target = (root / relative).resolve()
        if target.is_relative_to(root) and target.is_file():
            return target
    path = Path(item_path).expanduser()
    if path.is_absolute() and path.is_file():
        return path.resolve()
    source = Path(str((media_report.get("input") or {}).get("path", ""))).expanduser()
    roots = []
    if source.is_absolute():
        roots.append(source if source.is_dir() else source.parent)
    else:
        cwd_source = (Path.cwd() / source)
        roots.append(cwd_source if cwd_source.is_dir() else cwd_source.parent)
        report_source = (report_path.parent / source)
        roots.append(report_source if report_source.is_dir() else report_source.parent)
    roots.extend((report_path.parent, Path.cwd()))
    for root in roots:
        target = (root / path).resolve()
        if target.is_file():
            return target
    return None


def _asset_url(asset: Path, report_path: Path) -> str:
    relative = os.path.relpath(asset, report_path.parent).replace(os.sep, "/")
    return quote(relative, safe="/.:@+_-()")


def _portable_copy(asset: Path, item: dict[str, Any], report_path: Path) -> Path | None:
    """Copy an unchanged source asset beside the HTML, verifying its digest."""
    def digest_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    expected = str(item.get("sha256") or "").lower()
    digest = digest_file(asset)
    if expected and digest != expected:
        return None
    assets_dir = report_path.parent / f"{report_path.stem}_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    name = f"{digest}_{asset.name}"
    destination = assets_dir / name
    if not destination.exists():
        shutil.copy2(asset, destination)
    if digest_file(destination) != digest:
        destination.unlink(missing_ok=True)
        return None
    return destination


def build_evidence_gallery(media_report: dict[str, Any] | None,
                           report_path: str | Path, *, portable_media: bool = False) -> str:
    """Build escaped, browser-native media gallery markup for an HTML report."""
    if not media_report:
        return (
            '<p class="gallery-empty">No media report is linked to this case. '
            'Run the media extractor and save its JSON as '
            '<code>analysis/media_report.json</code> to include image and video evidence.</p>'
        )
    report_path = Path(report_path).resolve()
    media_items = [item for item in media_report.get("items", [])
                   if isinstance(item, dict) and item.get("kind") in {"image", "video"}]
    if not media_items:
        return '<p class="gallery-empty">The linked media report contains no image or video items.</p>'

    cards = []
    for index, item in enumerate(media_items):
        evidence_path = str(item.get("path", "Evidence file"))
        title = html.escape(Path(evidence_path).name or evidence_path)
        kind = item.get("kind")
        asset = _resolve_media_path(media_report, report_path, evidence_path)
        if asset and portable_media:
            asset = _portable_copy(asset, item, report_path)
        media_html = '<div class="gallery-unavailable">Evidence file could not be resolved from the media report.</div>'
        target_id = f"evidence-video-{index}"
        if asset and kind == "image":
            mime = item.get("mime") or mimetypes.guess_type(asset.name)[0] or "image/*"
            url = html.escape(_asset_url(asset, report_path), quote=True)
            media_html = (f'<img class="evidence-image" loading="lazy" src="{url}" '
                          f'alt="Evidence image: {title}" type="{html.escape(str(mime), quote=True)}">')
        elif asset and kind == "video":
            url = html.escape(_asset_url(asset, report_path), quote=True)
            media_html = (f'<video id="{target_id}" class="evidence-video" controls preload="metadata">'
                          f'<source src="{url}" type="{html.escape(str(item.get("mime") or "video/mp4"), quote=True)}">'
                          'This browser cannot play this video format.</video>')

        details = [f'<span>{html.escape(str(item.get("format", "Unknown format")))}</span>',
                   f'<span>{html.escape(str(item.get("size_bytes", "N/A")))} bytes</span>',
                   f'<span>Source: {html.escape(evidence_path)}</span>',
                   f'<span>Origin: {html.escape(str(item.get("origin", "unknown")))}</span>',
                   f'<span>Method: {html.escape(str(item.get("analysis_method", "format-specific extraction")))}</span>']
        if item.get("sha256"):
            details.append(f'<span class="hash">SHA-256 {html.escape(str(item["sha256"]))}</span>')
        anomalies = item.get("anomalies") or (item.get("metadata") or {}).get("flags") or []
        anomaly_html = (f'<details class="gallery-findings"><summary>{len(anomalies)} review finding(s)</summary>'
                        + '<ol>' + ''.join(
                            '<li><strong>' + html.escape(str(finding.get("type", "Finding"))) + '</strong> · '
                            + html.escape(str(finding.get("severity", "warning"))).upper() + ' · confidence '
                            + html.escape(str(finding.get("confidence", "unspecified"))) + '<br>'
                            + html.escape(json.dumps({k: v for k, v in finding.items()
                                                      if k not in {"type", "severity", "confidence", "note"}},
                                                     ensure_ascii=False, default=str))
                            + '<br>' + html.escape(str(finding.get("note", ""))) + '</li>'
                            for finding in anomalies if isinstance(finding, dict)) + '</ol></details>'
                        if anomalies else '<p class="gallery-clean">No review findings recorded for this item.</p>')
        extra = ""
        if kind == "video":
            timeline = item.get("frame_timeline") or {}
            frames = timeline.get("frames") or []
            if frames:
                buttons = []
                for frame in frames:
                    offset = frame.get("offset_s")
                    if isinstance(offset, (int, float)):
                        preview = frame.get("thumbnail_data_uri")
                        preview_html = (f'<img loading="lazy" class="frame-thumb" src="{html.escape(str(preview), quote=True)}" '
                                        f'alt="Video frame {html.escape(str(frame.get("frame_number", "?")))}">') if preview else ''
                        buttons.append(
                            f'<button type="button" class="frame-seek" data-video="{target_id}" '
                            f'data-seek="{float(offset):.6f}">{preview_html}<span>Frame '
                            f'{html.escape(str(frame.get("frame_number", "?")))} · +{float(offset):.3f}s</span></button>')
                if buttons:
                    extra += '<details class="frame-index"><summary>Frame timeline</summary><div class="frame-buttons">' + "".join(buttons) + "</div></details>"
            embedded = item.get("embedded_telemetry") or {}
            if embedded.get("status") not in (None, "no_embedded_telemetry_track"):
                formats = ", ".join(map(str, embedded.get("formats", []))) or "embedded telemetry"
                sensor_count = (embedded.get("gpmf") or {}).get("decoded_sensor_sample_count", 0)
                count_label = (f'{sensor_count:,} sensor sample(s)' if sensor_count
                               else f'{embedded.get("sample_count", 0):,} decoded sample(s)')
                extra += (f'<p class="gallery-telemetry">{html.escape(formats)} · '
                          f'{html.escape(str(count_label))}</p>')
        cards.append(
            f'<article class="evidence-card"><div class="evidence-media">{media_html}</div>'
            f'<div class="evidence-details"><h3>{title}</h3>'
            f'<span class="evidence-kind">{html.escape(str(kind).title())}</span>'
            f'<div class="evidence-meta">{"".join(details)}</div>{anomaly_html}{extra}'
            f'<details><summary>Evidence metadata</summary>{_metadata_table(item)}</details>'
            '</div></article>')

    return (f'<p class="gallery-summary">{len(media_items)} image/video item(s) · '
            f'{html.escape(str(media_report.get("generated_utc", "Media report timestamp unavailable")))}</p>'
            + ('<p class="portable-note">Verified copies of source media are stored beside this HTML report as report derivatives; the original evidence was not modified.</p>' if portable_media else '')
            + '<div class="evidence-gallery">' + "".join(cards) + '</div>'
            '<script>document.addEventListener("click",function(e){var b=e.target.closest(".frame-seek");'
            'if(!b)return;var v=document.getElementById(b.dataset.video);if(v){v.currentTime=Number(b.dataset.seek);'
            'v.play().catch(function(){});}});</script>')


def _metadata_table(item: dict[str, Any]) -> str:
    fields = (item.get("metadata") or {}).get("fields") or {}
    if not fields:
        return '<p>No normalized metadata fields were recorded.</p>'
    rows = []
    for key, detail in fields.items():
        if not isinstance(detail, dict):
            continue
        rows.append(f'<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(detail.get("value", "")))}</td>'
                    f'<td>{html.escape(str(detail.get("source", "unknown source")))}</td></tr>')
    return ('<table class="gallery-metadata"><thead><tr><th>Field</th><th>Value</th><th>Source</th></tr></thead>'
            '<tbody>' + "".join(rows) + '</tbody></table>')
