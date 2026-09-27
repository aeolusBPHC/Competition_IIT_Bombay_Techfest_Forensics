from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from analysis.normalized_security_indicators import (
    NormalizedSecurityIndicatorEngine,
)
from benchmark.metrics import calculate_metrics
from platform_parsers.common.registry import ParserRegistry


def load_ground_truth(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def collect_detected_indicators(
    security_indicators: dict[str, Any],
) -> set[str]:
    detected: set[str] = set()

    for category, values in security_indicators.items():

        if category in {
            "summary",
        }:
            continue

        if not isinstance(values, list):
            continue

        for indicator in values:
            if not isinstance(indicator, dict):
                continue

            indicator_type = indicator.get(
                "indicator_type"
            )

            if indicator_type:
                detected.add(indicator_type)

    return detected


def run_scenario(
    scenario: dict[str, Any],
    registry: ParserRegistry,
) -> dict[str, Any]:

    evidence_path = Path(
        scenario["evidence"]
    )

    parser = registry.get_parser(
        evidence_path
    )

    evidence = parser.parse()

    security_indicators = (
        NormalizedSecurityIndicatorEngine(
            evidence
        ).analyze()
    )

    detected = collect_detected_indicators(
        security_indicators
    )

    expected = set(
        scenario.get(
            "expected_indicators",
            [],
        )
    )

    metrics = calculate_metrics(
        expected=expected,
        detected=detected,
    )

    return {
        "scenario_id": scenario["scenario_id"],
        "platform": evidence.metadata.platform,
        "format": evidence.metadata.format,
        "evidence": str(evidence_path),
        "expected_indicators": sorted(expected),
        "detected_indicators": sorted(detected),
        "metrics": metrics.to_dict(),
        "record_counts": {
            "gps": len(evidence.gps),
            "navigation": len(evidence.navigation),
            "battery": len(evidence.battery),
            "telemetry": len(evidence.telemetry),
            "failsafe": len(evidence.failsafe),
            "commands": len(evidence.commands),
            "command_acks": len(
                evidence.command_acks
            ),
            "states": len(evidence.states),
            "parameters": len(
                evidence.parameters
            ),
            "events": len(evidence.events),
        },
    }


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Run the vendor-independent "
            "Drone Forensics benchmark."
        )
    )

    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path(
            "benchmark/ground_truth/labels.json"
        ),
        help="Ground-truth JSON file.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "benchmark/results/benchmark_results.json"
        ),
        help="Output benchmark result JSON.",
    )

    args = parser.parse_args()

    ground_truth = load_ground_truth(
        args.ground_truth
    )

    scenarios = ground_truth.get(
        "scenarios",
        [],
    )

    registry = ParserRegistry()

    results = []

    for scenario in scenarios:

        print(
            f"Running scenario: "
            f"{scenario.get('scenario_id', 'UNKNOWN')}"
        )

        try:

            result = run_scenario(
                scenario,
                registry,
            )

            results.append(result)

            metrics = result["metrics"]

            print(
                f"  Platform: "
                f"{result['platform']}"
            )

            print(
                f"  Detected: "
                f"{len(result['detected_indicators'])}"
            )

            print(
                f"  Expected: "
                f"{len(result['expected_indicators'])}"
            )

            print(
                f"  Precision: "
                f"{metrics['precision']:.3f}"
            )

            print(
                f"  Recall: "
                f"{metrics['recall']:.3f}"
            )

            print(
                f"  F1: "
                f"{metrics['f1']:.3f}"
            )

        except Exception as exc:

            print(
                f"  ERROR: {exc}"
            )

            results.append(
                {
                    "scenario_id": scenario.get(
                        "scenario_id",
                        "UNKNOWN",
                    ),
                    "error": str(exc),
                }
            )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = {
        "benchmark": {
            "name": "Drone Forensics Benchmark",
            "version": "1.0",
        },
        "scenario_count": len(
            scenarios
        ),
        "results": results,
    }

    with args.output.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print()
    print(
        f"Benchmark results saved to: "
        f"{args.output}"
    )


if __name__ == "__main__":
    main()
