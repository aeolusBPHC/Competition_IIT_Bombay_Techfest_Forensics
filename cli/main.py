import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def get_evidence_path(case_id, evidence_id):
    return (
        BASE_DIR
        / "repository"
        / "cases"
        / case_id
        / evidence_id
        / "evidence"
    )


def get_analysis_path(case_id, evidence_id):
    return (
        BASE_DIR
        / "repository"
        / "cases"
        / case_id
        / evidence_id
        / "analysis"
    )


# ============================================================
# ACQUIRE
# ============================================================

def command_acquire(args):
    print("=" * 70)
    print("DRONE FORENSICS TOOLKIT - EVIDENCE ACQUISITION")
    print("=" * 70)

    print(f"Input evidence : {args.input}")
    print(f"Case ID        : {args.case}")

    print("\n[INFO] Acquisition module selected.")
    print("[INFO] SHA-256 hashing and chain-of-custody processing will run.")

    from acquisition.acquire import acquire_evidence

    acquire_evidence(
        input_file=args.input,
        case_id=args.case
    )


# ============================================================
# ANALYZE
# ============================================================

def command_analyze(args):
    print("=" * 70)
    print("DRONE FORENSICS TOOLKIT - EVIDENCE ANALYSIS")
    print("=" * 70)

    print(f"Case ID    : {args.case}")
    print(f"Evidence   : {args.evidence}")

    evidence_dir = get_evidence_path(
        args.case,
        args.evidence
    )

    ulg_files = list(evidence_dir.glob("*.ulg"))

    if not ulg_files:
        raise FileNotFoundError(
            f"No ULog evidence found in {evidence_dir}"
        )

    ulg_path = ulg_files[0]

    print(f"ULog       : {ulg_path}")

    print("\n[1/6] ULog parsing")
    print("[2/6] GPS extraction")
    print("[3/6] Navigation integrity analysis")
    print("[4/6] Command/ACK forensics")
    print("[5/6] State reconstruction")
    print("[6/6] Security indicators")

    print("\n[INFO] Analysis modules will be executed.")


# ============================================================
# REPORT
# ============================================================

def command_report(args):
    print("=" * 70)
    print("DRONE FORENSICS TOOLKIT - REPORT GENERATION")
    print("=" * 70)

    print(f"Case ID    : {args.case}")
    print(f"Evidence   : {args.evidence}")

    print("\n[INFO] Generating forensic HTML report.")

    from reporting.report_generator import generate_report

    generate_report()


# ============================================================
# NORMALIZED ANALYSIS
# ============================================================

def command_normalized_analysis(args):
    print("=" * 70)
    print("DRONE FORENSICS TOOLKIT - NORMALIZED ANALYSIS")
    print("=" * 70)

    source = Path(args.input).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()

    # --------------------------------------------------------
    # INPUT VALIDATION
    # --------------------------------------------------------

    if not source.exists():
        raise FileNotFoundError(
            f"Input evidence does not exist:\n{source}"
        )

    if not source.is_file():
        raise ValueError(
            f"Input evidence is not a file:\n{source}"
        )

    print(f"\nInput evidence : {source}")
    print(f"Output report  : {output}")

    # --------------------------------------------------------
    # STEP 1 — EVIDENCE PROVENANCE
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("[1/5] EVIDENCE PROVENANCE")
    print("=" * 70)

    evidence_dir = source.parent.parent
    metadata_path = evidence_dir / "metadata.json"

    case_id = None
    evidence_id = None
    evidence_hash = None

    if metadata_path.exists():
        print(
            f"[INFO] Acquisition metadata: "
            f"{metadata_path}"
        )

        with metadata_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            acquisition_metadata = json.load(file)

        case_id = acquisition_metadata.get(
            "case_id"
        )

        evidence_id = acquisition_metadata.get(
            "evidence_id"
        )

        evidence_hash = acquisition_metadata.get(
            "forensic_copy_hash"
        )

        acquired_file = acquisition_metadata.get(
            "acquired_file"
        )

        print(
            f"[OK] Case ID       : {case_id}"
        )

        print(
            f"[OK] Evidence ID   : {evidence_id}"
        )

        print(
            f"[OK] Evidence hash : {evidence_hash}"
        )

        if acquired_file:
            acquired_path = Path(
                acquired_file
            ).resolve()

            if acquired_path != source:
                raise ValueError(
                    "Evidence path does not match "
                    "the acquired forensic copy recorded "
                    "in metadata.json.\n"
                    f"Metadata path: {acquired_path}\n"
                    f"Input path   : {source}"
                )

        if not acquisition_metadata.get(
            "integrity_verified",
            False,
        ):
            raise ValueError(
                "Acquisition metadata does not indicate "
                "that forensic-copy integrity was verified."
            )

    else:
        print(
            "[INFO] No acquisition metadata found."
        )

        print(
            "[INFO] Calculating SHA-256 directly "
            "from the supplied evidence file."
        )

        from reporting.normalized_report import (
            NormalizedForensicReport,
        )

        evidence_hash = (
            NormalizedForensicReport.calculate_sha256(
                source
            )
        )

        print(
            f"[OK] Calculated evidence hash : "
            f"{evidence_hash}"
        )

    # --------------------------------------------------------
    # STEP 2 — PLATFORM DETECTION
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("[2/5] PLATFORM DETECTION")
    print("=" * 70)

    from platform_parsers.common.registry import (
        ParserRegistry,
    )

    registry = ParserRegistry()

    detection = registry.detect(source)

    if not detection.get(
        "supported",
        False,
    ):
        raise ValueError(
            f"Unsupported evidence format: {source}"
        )

    print(
        f"[OK] Platform   : "
        f"{detection['platform']}"
    )

    print(
        f"[OK] Format     : "
        f"{detection['format']}"
    )

    print(
        f"[OK] Confidence : "
        f"{detection['confidence']}"
    )

    print(
        f"[OK] Reason     : "
        f"{detection['reason']}"
    )

    # --------------------------------------------------------
    # STEP 3 — NORMALIZED PARSING
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("[3/5] NORMALIZED PARSING")
    print("=" * 70)

    parser = registry.get_parser(source)

    print(
        f"[INFO] Using parser: "
        f"{parser.__class__.__name__}"
    )

    evidence = parser.parse()

    print("[OK] Evidence normalized.")

    # --------------------------------------------------------
    # STEP 4 — NORMALIZED ANALYSIS
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("[4/5] NORMALIZED ANALYSIS")
    print("=" * 70)

    from reporting.normalized_report import (
        NormalizedForensicReport,
    )

    hash_source = (
        "acquisition_metadata"
        if metadata_path.exists()
        else "calculated_from_input"
    )

    report = NormalizedForensicReport(
        evidence,
        evidence_hash=evidence_hash,
        evidence_id=evidence_id,
        case_id=case_id,
        evidence_hash_source=hash_source,
    )

    report_data = report.build()

    print(
        f"[OK] GPS records      : "
        f"{report_data['record_counts']['gps']}"
    )

    print(
        f"[OK] Commands         : "
        f"{report_data['record_counts']['commands']}"
    )

    print(
        f"[OK] Command ACKs     : "
        f"{report_data['record_counts']['command_acks']}"
    )

    print(
        f"[OK] State records    : "
        f"{report_data['record_counts']['states']}"
    )

    print(
        f"[OK] Parameter records: "
        f"{report_data['record_counts']['parameters']}"
    )

    print(
        f"[OK] Forensic events  : "
        f"{report_data['record_counts']['events']}"
    )

    for category in ("navigation", "trajectory", "battery", "telemetry", "failsafe"):
        print(f"[OK] {category.capitalize():18s}: {report_data['record_counts'][category]}")

    # --------------------------------------------------------
    # SECURITY ANALYSIS SUMMARY
    # --------------------------------------------------------

    security_indicators = report_data.get(
        "security_indicators",
        {}
    )

    findings = report_data.get(
        "findings",
        []
    )

    total_indicators = sum(
        len(value)
        for key, value in security_indicators.items()
        if key != "summary"
        and isinstance(value, list)
    )

    print(
        f"[OK] Security indicators: "
        f"{total_indicators}"
    )

    print(
        f"[OK] Forensic findings : "
        f"{len(findings)}"
    )

    # --------------------------------------------------------
    # STEP 5 — REPORT GENERATION
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("[5/5] REPORT GENERATION")
    print("=" * 70)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    saved_path = report.save(output, report_data=report_data)

    print(
        f"[OK] Report saved: "
        f"{saved_path}"
    )

    hash_path = Path(
        str(saved_path) + ".sha256"
    )

    if hash_path.exists():
        print(
            f"[OK] Report hash : "
            f"{hash_path}"
        )

        report_hash = (
            hash_path
            .read_text(
                encoding="utf-8"
            )
            .strip()
            .split()[0]
        )

        print(
            f"[OK] SHA-256      : "
            f"{report_hash}"
        )

    print("\n" + "=" * 70)
    print("NORMALIZED ANALYSIS COMPLETE")
    print("=" * 70)

# ============================================================
# CASE
# ============================================================

def command_case(args):
    print("=" * 70)
    print("DRONE FORENSICS TOOLKIT")
    print("=" * 70)

    print(f"\nCase ID: {args.case}")

    print("\nAvailable operations:")
    print("  1. Evidence acquisition")
    print("  2. Evidence preservation")
    print("  3. ULog analysis")
    print("  4. GPS analysis")
    print("  5. Navigation integrity")
    print("  6. Command/ACK forensics")
    print("  7. State reconstruction")
    print("  8. Security indicators")
    print("  9. Forensic report")
    print(" 10. End-to-end processing")


# ============================================================
# PROCESS
# ============================================================

def command_process(args):
    from cli.pipeline import process_evidence
    return process_evidence(args)


# ============================================================
# ARGUMENT PARSER
# ============================================================

def command_trajectory_predict(args):
    from ml.trajectory_inference import run
    return run(args)


def build_parser():

    parser = argparse.ArgumentParser(
        description="Indigenous Drone Forensics Toolkit"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True
    )

    # Keep PyTorch optional for the rest of the forensic CLI.
    forecast = subparsers.add_parser("trajectory-predict", help="Forecast with a saved trajectory checkpoint")
    forecast.add_argument("--input", required=True)
    forecast.add_argument("--checkpoint", required=True)
    forecast.add_argument("--output", required=True)
    forecast.add_argument("--report")
    forecast.add_argument("--pdf", action="store_true", help="Also export --report as PDF (requires --report)")
    forecast.add_argument("--case-id")
    forecast.add_argument("--at-time", type=float)
    forecast.add_argument("--predictor", choices=("selected", "gru", "constant_velocity", "constant_acceleration"), default="selected")
    forecast.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    forecast.set_defaults(func=command_trajectory_predict)

    # --------------------------------------------------------
    # ACQUIRE
    # --------------------------------------------------------

    acquire = subparsers.add_parser(
        "acquire",
        help="Acquire and preserve drone evidence"
    )

    acquire.add_argument(
        "--input",
        required=True,
        help="Path to source evidence"
    )

    acquire.add_argument(
        "--case",
        required=True,
        help="Case identifier"
    )

    acquire.set_defaults(func=command_acquire)

    # --------------------------------------------------------
    # ANALYZE
    # --------------------------------------------------------

    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze acquired drone evidence"
    )

    analyze.add_argument(
        "--case",
        required=True,
        help="Case identifier"
    )

    analyze.add_argument(
        "--evidence",
        required=True,
        help="Evidence identifier"
    )

    analyze.set_defaults(func=command_analyze)

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    report = subparsers.add_parser(
        "report",
        help="Generate forensic report"
    )

    report.add_argument(
        "--case",
        required=True,
        help="Case identifier"
    )

    report.add_argument(
        "--evidence",
        required=True,
        help="Evidence identifier"
    )

    report.set_defaults(func=command_report)

    # --------------------------------------------------------
    # NORMALIZED ANALYSIS
    # --------------------------------------------------------

    normalized_analysis = subparsers.add_parser(
        "normalized-analysis",
        help="Automatically detect, parse, analyze, and report evidence"
    )

    normalized_analysis.add_argument(
        "--input",
        required=True,
        help="Path to evidence file"
    )

    normalized_analysis.add_argument(
        "--output",
        required=True,
        help="Path for normalized JSON report"
    )

    normalized_analysis.set_defaults(
        func=command_normalized_analysis
    )

    # --------------------------------------------------------
    # CASE
    # --------------------------------------------------------

    case = subparsers.add_parser(
        "case",
        help="Display case information"
    )

    case.add_argument(
        "--case",
        required=True,
        help="Case identifier"
    )

    case.set_defaults(func=command_case)

    # --------------------------------------------------------
    # PROCESS
    # --------------------------------------------------------

    process = subparsers.add_parser(
        "process",
        help="Run end-to-end forensic processing"
    )

    process.add_argument(
        "--input",
        required=True,
        help="Path to a supported flight log"
    )

    process.add_argument("--case", help="Case identifier (generated if omitted)")
    process.add_argument("--output", help="New directory for this run's reports")
    process.add_argument("--media", help="Optional media file, directory, or disk image")
    process.add_argument("--portable-media", action="store_true",
                         help="Copy verified media beside the HTML report")
    process.add_argument("--checkpoint", help="Optional trained trajectory checkpoint")
    process.add_argument("--pdf", action="store_true",
                         help="Also export forensic and requested forecast HTML reports as PDF")

    process.set_defaults(func=command_process)

    return parser


# ============================================================
# MAIN
# ============================================================

def main():

    parser = build_parser()

    args = parser.parse_args()

    try:
        args.func(args)

    except KeyboardInterrupt:
        print("\n[ERROR] Operation interrupted.")
        sys.exit(1)

    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
