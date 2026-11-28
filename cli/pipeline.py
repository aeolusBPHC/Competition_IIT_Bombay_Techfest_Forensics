"""Acquire, analyze and report one supported log, with optional media/forecast."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from acquisition.acquire import acquire_evidence, calculate_sha256
from acquisition.custody import append_custody_event, trust_directory, verify_custody


def process_evidence(args):
    from cli.main import command_normalized_analysis
    from platform_parsers.common.registry import ParserRegistry
    from reporting.normalized_report_generator import generate_report

    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Input must be an existing flight-log file: {source}")
    case = args.case or f"CASE-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", case):
        raise ValueError("Case must contain only letters, digits, hyphens and underscores.")
    with source.open("rb") as stream:
        is_lfs_pointer = stream.read(64).startswith(b"version https://git-lfs.github.com/spec/v1")
    if is_lfs_pointer:
        raise ValueError("Input is a Git LFS pointer; install Git LFS and run git lfs pull.")
    if not (ParserRegistry().detect(source) or {}).get("supported"):
        raise ValueError(f"Unsupported flight-log format: {source}")
    media = Path(args.media).expanduser().resolve() if args.media else None
    checkpoint = Path(args.checkpoint).expanduser().resolve() if args.checkpoint else None
    if media and not media.exists():
        raise ValueError(f"Media does not exist: {media}")
    if args.portable_media and not media:
        raise ValueError("--portable-media requires --media")
    if checkpoint and not checkpoint.is_file():
        raise ValueError(f"Checkpoint does not exist: {checkpoint}")
    pdf_requested = getattr(args, "pdf", False)
    if pdf_requested:
        from reporting.pdf_export import check_pdf_support
        check_pdf_support()
    output = Path(args.output).expanduser().resolve() if args.output else None
    if output:
        trusted_folder = trust_directory(getattr(args, "trust_dir", None))
        if trusted_folder.is_relative_to(output) or output.is_relative_to(trusted_folder):
            raise ValueError("The trusted checkpoint store must be separate from report output.")
        # Never write reports into source evidence or overwrite a previous run.
        if media and media.is_dir() and output.is_relative_to(media):
            raise ValueError("Output must be outside the media evidence directory.")
        output.mkdir(parents=True, exist_ok=False)

    operator = getattr(args, "operator", "drone_forensics")
    trust_dir = getattr(args, "trust_dir", None)
    acquired = acquire_evidence(str(source), case, operator=operator, trust_dir=trust_dir)
    copy = Path(acquired["acquired_file"])
    case_directory = copy.parent.parent
    checkpoint_reference = Path(acquired["custody_checkpoint"])

    def record(event, description, details=None):
        return append_custody_event(case_directory, checkpoint_reference, event=event,
                                    operator=operator, description=description, details=details)

    expected = acquired["forensic_copy_hash"]
    if not acquired["integrity_verified"] or calculate_sha256(copy) != expected:
        raise ValueError("Acquired flight-log integrity verification failed")
    if output is None:
        output = copy.parent.parent / "results"
        output.mkdir()

    normalized = output / "normalized_report.json"
    command_normalized_analysis(argparse.Namespace(input=str(copy), output=str(normalized)))
    record("ANALYSIS_COMPLETED", "Normalized forensic analysis completed.",
           {"report_sha256": calculate_sha256(normalized)})
    media_report = None
    media_metadata = None
    if media:
        from media.extractor import main as extract_media
        # Files/images receive the same acquisition and custody records as logs.
        if media.is_file():
            media_metadata = acquire_evidence(str(media), case, operator=operator, trust_dir=trust_dir)
            if not media_metadata["integrity_verified"]:
                raise ValueError("Media acquisition integrity verification failed")
            media = Path(media_metadata["acquired_file"])
        media_report = output / "media_report.json"
        extract_media(["--input", str(media), "--output", str(media_report),
                       "--keep-recovered", str(output / "recovered_media")])
        record("MEDIA_EXAMINED", "Requested media examination completed.",
               {"report_sha256": calculate_sha256(media_report)})
        if media_metadata is not None:
            media_case = Path(media_metadata["acquired_file"]).parent.parent
            append_custody_event(media_case, media_metadata["custody_checkpoint"],
                                 event="MEDIA_EXAMINED", operator=operator,
                                 description="Acquired media examined without modifying its source.",
                                 details={"report_sha256": calculate_sha256(media_report)})

    artifacts = {"normalized_report": str(normalized)}
    if media_report:
        artifacts["media_report"] = str(media_report)
    if checkpoint:
        from ml.trajectory_inference import main as predict
        forecast, forecast_html = output / "trajectory_forecast.json", output / "trajectory_forecast.html"
        predict(["--input", str(copy), "--checkpoint", str(checkpoint), "--case-id", case,
                 "--output", str(forecast), "--report", str(forecast_html)])
        artifacts.update(trajectory_forecast=str(forecast), trajectory_html=str(forecast_html))
        record("FORECAST_GENERATED", "Requested trajectory forecast completed; estimates are separate from recorded evidence.",
               {"forecast_sha256": calculate_sha256(forecast)})

    html = output / "forensic_report.html"
    generate_report(normalized, html, media_report_path=media_report,
                    portable_media=args.portable_media)
    artifacts["html_report"] = str(html)
    if pdf_requested:
        from reporting.pdf_export import export_pdf
        artifacts["pdf_report"] = str(export_pdf(html))
        if checkpoint:
            artifacts["trajectory_pdf"] = str(export_pdf(forecast_html))
    if calculate_sha256(copy) != expected:
        raise ValueError("Flight-log integrity changed during processing")
    record("REPORTS_GENERATED", "Requested report files generated; workflow completion requires final integrity checks.",
           {"html_sha256": calculate_sha256(html), "pdf_requested": pdf_requested})
    custody_state = verify_custody(case_directory, checkpoint_reference)
    if media_metadata is not None:
        custody_state["related_media"] = [verify_custody(
            Path(media_metadata["acquired_file"]).parent.parent, media_metadata["custody_checkpoint"])]
    custody_report = output / "custody_verification.json"
    custody_report.write_text(json.dumps(custody_state, indent=2) + "\n", encoding="utf-8")
    artifacts["custody_verification"] = str(custody_report)
    # Includes plots, media derivatives and forecast outputs, not just the main JSON.
    hashes = {}
    for path in sorted(output.rglob("*")):
        if path.is_file():
            digest = calculate_sha256(path)
            hashes[str(path.relative_to(output))] = digest
    manifest = {"status": "complete", "case_id": case,
                "evidence_id": acquired["evidence_id"], "acquired_log": str(copy),
                "log_sha256": expected, "log_integrity_reverified": True,
                "artifacts": artifacts, "sha256": hashes,
                "media_requested": bool(args.media), "forecast_requested": bool(checkpoint),
                "pdf_requested": pdf_requested}
    manifest["custody"] = custody_state
    if pdf_requested:
        manifest["pdf_options"] = {"max_items_per_table_or_list": 100,
                                   "omissions_labeled_in_pdf": True}
    manifest_path = output / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for path in (html, manifest_path):
        Path(str(path) + ".sha256").write_text(
            f"{calculate_sha256(path)}  {path.name}\n", encoding="utf-8")
    print(f"\nComplete. Open: {html}\nRun manifest: {manifest_path}")
    if pdf_requested:
        print(f"PDF report: {artifacts['pdf_report']}")
        if checkpoint:
            print(f"Forecast PDF: {artifacts['trajectory_pdf']}")
    return manifest
