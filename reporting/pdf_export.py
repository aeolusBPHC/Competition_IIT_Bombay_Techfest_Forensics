"""Print toolkit HTML reports to PDF without rerunning evidence analysis."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement


PRINT_CSS = """
@page {
    size: A4;
    margin: 16mm 13mm 19mm;
    @bottom-left { content: "Drone Forensics Toolkit"; font: 8pt sans-serif; color: #687078; }
    @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 8pt sans-serif; }
}
html, body { background: white !important; }
body { font: 10pt Arial, sans-serif !important; margin: 0 !important; padding: 0 !important; }
.container { max-width: none !important; margin: 0 !important; padding: 0 !important; }
header { padding: 12pt !important; border-radius: 0 !important; }
header h1, h1 { font-size: 20pt !important; }
h2 { font-size: 15pt; } h3 { font-size: 12pt; }
h1, h2, h3, summary { break-after: avoid; }
section { break-inside: auto !important; padding: 8pt 0 !important; border: 0 !important;
          box-shadow: none !important; border-radius: 0 !important; }
table { width: 100% !important; table-layout: fixed; border-collapse: collapse; }
th, td { padding: 4pt !important; overflow-wrap: anywhere; vertical-align: top; }
.info-table th, .nested-table th { width: 30% !important; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
pre, code { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 8pt; }
ul, ol { margin-left: 0; padding-left: 12pt; }
.pdf-key-values { margin: 3pt 0; padding-left: 5pt; border-left: 1px solid #dfe4e8; }
.pdf-key-values strong { color: #24506b; }
img { max-width: 100% !important; max-height: 210mm !important; object-fit: contain; }
.plot-card { break-inside: avoid; }
.summary-cards, .evidence-gallery, .evidence-media, .frame-buttons { display: block !important; }
.card { display: inline-block; width: 28%; margin: 3pt; padding: 6pt !important; }
.card-number { font-size: 16pt !important; }
.evidence-card { overflow: visible !important; margin-bottom: 12pt; }
.evidence-media { min-height: 0 !important; background: white !important; }
.evidence-details { padding: 6pt !important; }
.frame-buttons, .filesystem-timeline-scroll { max-height: none !important; overflow: visible !important; }
.frame-seek { display: inline-block !important; vertical-align: top; margin: 3pt; }
details, details > * { display: block !important; }
video, audio, script { display: none !important; }
.pdf-note { border: 1px solid #b7791f; background: #fff8e8; padding: 8pt; margin-bottom: 12pt; }
.pdf-omitted { color: #68571e; background: #fff8e8; font-style: italic; }
"""


def _prepare_print_tree(root, max_items):
    """Bound large appendices before layout, retaining an explicit omission label."""
    limited = 0
    pending = [root]
    while pending:
        element = pending.pop()
        if element.tag == "details":
            element.set("open", "")
        item_tag = {"tbody": "tr", "ul": "li", "ol": "li"}.get(element.tag)
        if max_items and item_tag:
            items = [child for child in element if child.tag == item_tag]
            if len(items) > max_items:
                for child in items[max_items:]:
                    element.remove(child)
                label = SubElement(element, item_tag, {"class": "pdf-omitted"})
                if item_tag == "tr":
                    label = SubElement(label, "td", {"colspan": str(max(1, len(items[0])))})
                label.text = (
                    f"PDF preview: {max_items} of {len(items)} items shown; "
                    f"{len(items) - max_items} omitted. See the complete HTML and JSON artifacts."
                )
                limited += 1
        pending.extend(reversed(list(element)))
    # Repeatedly nesting two-column tables squeezes deep raw fields into tiny
    # columns. Print those dictionaries as key/value blocks at the available width.
    for table in list(root.iter("table")):
        if "nested-table" not in table.get("class", "").split():
            continue
        table.tag = "div"
        table.set("class", "pdf-key-values")
        for group in table:
            if group.tag not in {"tbody", "thead"}:
                continue
            group.tag = "div"
            for row in group:
                row.tag = "div"
                for cell in row:
                    if cell.tag == "th":
                        cell.tag = "strong"
                        cell.tail = ": " + (cell.tail or "")
                    elif cell.tag == "td":
                        cell.tag = "span"
    return limited


def check_pdf_support():
    """Fail before acquisition if the explicitly requested renderer is unavailable."""
    try:
        from weasyprint import CSS, HTML
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "PDF export requires WeasyPrint and its system libraries. "
            "Run python3 -m pip install -r requirements-pdf.txt; "
            "see the README PDF installation instructions."
        ) from exc
    return HTML, CSS


def export_pdf(input_html, output_pdf=None, *, max_items=100):
    """Export an HTML report and a SHA-256 sidecar; never replace existing files."""
    source = Path(input_html).expanduser().resolve()
    if max_items < 0:
        raise ValueError("--max-items must be nonnegative; use 0 to include every item")
    target = Path(output_pdf).expanduser().resolve() if output_pdf else source.with_suffix(".pdf")
    if not source.is_file():
        raise ValueError(f"HTML report does not exist: {source}")
    if source.suffix.lower() not in {".html", ".htm"}:
        raise ValueError("Input must be an HTML report (.html or .htm).")
    if target.suffix.lower() != ".pdf":
        raise ValueError("PDF output must end in .pdf")
    sidecar = Path(str(target) + ".sha256")
    if target.exists() or sidecar.exists():
        raise FileExistsError(f"PDF or checksum already exists; choose a new output: {target}")
    HTML, CSS = check_pdf_support()
    from weasyprint.urls import FatalURLFetchingError, URLFetcher

    # Never silently publish a PDF with missing plots or media resources.
    fetcher = URLFetcher(allowed_protocols=("file", "data"), fail_on_errors=True)
    document = HTML(filename=str(source), url_fetcher=fetcher)
    body = document.etree_element.find("body")
    if body is not None:
        limited = _prepare_print_tree(body, max_items)
        note = Element("p", {"class": "pdf-note"})
        note.text = (
            "Static PDF export. Video playback and interactive controls require the HTML report. "
            "Source evidence and machine-readable results remain separate artifacts."
        )
        if limited:
            note.text += (
                f" {limited} long table/list preview(s) are limited to the first {max_items} items each; "
                "omissions are labeled below. Consult the complete HTML and JSON for all items."
            )
        body.insert(0, note)
    try:
        content = document.write_pdf(stylesheets=[CSS(string=PRINT_CSS)])
    except FatalURLFetchingError as exc:
        raise RuntimeError(f"PDF resource could not be loaded: {exc}") from exc
    if not content.startswith(b"%PDF-"):
        raise RuntimeError("PDF renderer did not return a valid PDF header")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(content)
    digest = hashlib.sha256(content).hexdigest()
    with sidecar.open("x", encoding="utf-8") as stream:
        stream.write(f"{digest}  {target.name}\n")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Existing toolkit HTML report")
    parser.add_argument("--output", help="New PDF path; defaults to the HTML name with .pdf")
    parser.add_argument("--max-items", type=int, default=100,
                        help="Items per table/list preview (default: 100; 0 includes all)")
    args = parser.parse_args(argv)
    try:
        output = export_pdf(args.input, args.output, max_items=args.max_items)
    except (ValueError, FileExistsError, RuntimeError) as exc:
        parser.exit(1, f"[ERROR] {exc}\n")
    print(f"PDF report: {output}\nSHA-256: {output}.sha256")


if __name__ == "__main__":
    main()
