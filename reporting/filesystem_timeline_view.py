"""Render the read-only removable-media timeline in the main case report."""

from __future__ import annotations

import html
from typing import Any


def build_filesystem_timeline(timeline: dict[str, Any] | None,
                              display_limit: int = 1000) -> str:
    if not timeline:
        return ('<p class="timeline-empty">No removable-media filesystem timeline is linked. '
                'Run the media extractor on a raw disk image to include one.</p>')
    status = html.escape(str(timeline.get("status", "unknown")))
    summary = timeline.get("summary") or {}
    summary_html = (
        '<p class="filesystem-timeline-summary">'
        f'{html.escape(str(summary.get("entry_count", 0)))} entries · '
        f'{html.escape(str(summary.get("allocated_entries", 0)))} allocated · '
        f'{html.escape(str(summary.get("deleted_entries", 0)))} marked deleted · '
        f'{html.escape(str(summary.get("event_count", 0)))} timestamp events · '
        f'status: {status}</p>'
    )
    notes = timeline.get("timestamp_notes") or []
    notes_html = ("<ul class=\"filesystem-timeline-notes\">" + "".join(
        f"<li>{html.escape(str(note))}</li>" for note in notes
    ) + "</ul>") if notes else ""
    warnings = timeline.get("warnings") or []
    warnings_html = ("<ul class=\"filesystem-timeline-warnings\">" + "".join(
        f"<li>{html.escape(str(warning))}</li>" for warning in warnings
    ) + "</ul>") if warnings else ""
    events = timeline.get("events") or []
    if not events:
        return summary_html + notes_html + warnings_html + (
            '<p class="timeline-empty">No filesystem timestamp events were available.</p>'
        )

    rows = []
    for event in events[:display_limit]:
        status_class = "deleted" if str(event.get("entry_status", "")).startswith("deleted_entry") else "allocated"
        rows.append(
            '<tr>'
            f'<td>{html.escape(str(event.get("time_utc", "")))}</td>'
            f'<td>{html.escape(str(event.get("timestamp_type", "")))}</td>'
            f'<td class="filesystem-path">{html.escape(str(event.get("path", "")))}</td>'
            f'<td>{html.escape(str(event.get("filesystem_type") or "unknown filesystem"))}</td>'
            f'<td class="filesystem-{status_class}">{html.escape(str(event.get("entry_status", "")))}</td>'
            f'<td>{html.escape(str(event.get("meaning_and_limits", "")))}</td>'
            '</tr>'
        )
    table = (
        '<div class="filesystem-timeline-scroll"><table class="filesystem-timeline-table">'
        '<thead><tr><th>Timestamp (UTC rendering)</th><th>Filesystem field</th>'
        '<th>Path</th><th>Filesystem</th><th>Entry status</th><th>Meaning and limits</th></tr></thead>'
        '<tbody>' + "".join(rows) + '</tbody></table></div>'
    )
    truncation = ""
    if len(events) > display_limit:
        truncation = (f'<p>Showing the first {display_limit} of {len(events)} events. '
                      'The complete timeline is in the media extractor JSON.</p>')
    return summary_html + notes_html + warnings_html + truncation + table
