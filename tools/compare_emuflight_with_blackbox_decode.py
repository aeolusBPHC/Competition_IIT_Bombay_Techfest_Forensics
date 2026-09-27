"""
Cross-check the EmuFlight decoder against the reference blackbox_decode
(from the open-source blackbox-tools project) on a REAL log.

    blackbox_decode --unit-vbat raw --unit-amperage raw LOG00001.BFL
    python -m tools.compare_emuflight_with_blackbox_decode LOG00001.BFL LOG00001.01.csv --log-index 0

blackbox_decode numbers logs from 1 (LOG00001.01.csv is log index 0).
Only integer columns whose names match decoded main-frame fields are
compared; unit suffixes like "time (us)" are stripped. Exit code 1 on
any mismatch.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys

from platform_parsers.emuflight.blackbox_decoder import decode_file


def _clean(name: str) -> str:
    return re.sub(r"\s*\(.*\)\s*$", "", name.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log_file")
    ap.add_argument("reference_csv")
    ap.add_argument("--log-index", type=int, default=0)
    ap.add_argument("--max-report", type=int, default=20)
    args = ap.parse_args()

    logs = [log for log in decode_file(args.log_file) if log.index == args.log_index]
    if not logs:
        print(f"No log with index {args.log_index} in {args.log_file}")
        return 1
    ours = {f["loopIteration"]: f for f in logs[0].main_frames}

    with open(args.reference_csv, newline="") as fh:
        reader = csv.reader(fh)
        header = [_clean(h) for h in next(reader)]
        rows = list(reader)

    field_names = set(next(iter(ours.values())).keys()) if ours else set()
    columns = [(i, h) for i, h in enumerate(header) if h in field_names]
    print(f"Comparing {len(columns)} columns: {[h for _, h in columns]}")

    it_col = header.index("loopIteration")
    compared = missing = mismatches = 0
    for row in rows:
        try:
            iteration = int(row[it_col])
        except (ValueError, IndexError):
            continue
        frame = ours.get(iteration)
        if frame is None:
            missing += 1
            continue
        compared += 1
        for idx, name in columns:
            try:
                ref = int(row[idx])
            except (ValueError, IndexError):
                continue  # non-integer column (e.g. converted units)
            if frame[name] != ref:
                mismatches += 1
                if mismatches <= args.max_report:
                    print(f"MISMATCH iteration {iteration} {name}: ours={frame[name]} ref={ref}")

    print(f"Reference rows: {len(rows)} | compared: {compared} | "
          f"missing in ours: {missing} | ours total: {len(ours)} | mismatched values: {mismatches}")
    print(f"Decoder stats: {logs[0].stats.as_dict()}")
    return 1 if mismatches or missing else 0


if __name__ == "__main__":
    sys.exit(main())
