import json
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

CASE_ID = "CASE-001"
EVIDENCE_ID = "EVD-20260919-175126"

EVIDENCE_DIR = (
    BASE_DIR
    / "repository"
    / "cases"
    / CASE_ID
    / EVIDENCE_ID
)

ANALYSIS_DIR = EVIDENCE_DIR / "analysis"

OUTPUT_DIR = BASE_DIR / "reporting" / "plots"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# HELPERS
# ============================================================

def load_json(filename):

    path = ANALYSIS_DIR / filename

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 1. GPS FLIGHT PATH
# ============================================================

def plot_gps_path():

    csv_path = ANALYSIS_DIR / "gps_data.csv"

    df = pd.read_csv(csv_path)

    required = [
        "latitude_deg",
        "longitude_deg"
    ]

    for column in required:
        if column not in df.columns:
            raise ValueError(
                f"Missing GPS column: {column}"
            )

    plt.figure(figsize=(10, 8))

    plt.plot(
        df["longitude_deg"],
        df["latitude_deg"],
        linewidth=1
    )

    plt.scatter(
        df["longitude_deg"].iloc[0],
        df["latitude_deg"].iloc[0],
        s=80,
        marker="o",
        label="Start"
    )

    plt.scatter(
        df["longitude_deg"].iloc[-1],
        df["latitude_deg"].iloc[-1],
        s=80,
        marker="x",
        label="End"
    )

    plt.xlabel("Longitude")
    plt.ylabel("Latitude")

    plt.title(
        f"GPS Flight Path — {CASE_ID}"
    )

    plt.legend()
    plt.grid(True)

    plt.tight_layout()

    output = OUTPUT_DIR / "gps_flight_path.png"

    plt.savefig(
        output,
        dpi=200
    )

    plt.close()

    print(f"Created: {output}")


# ============================================================
# 2. ALTITUDE AND SPEED
# ============================================================

def plot_altitude_speed():

    csv_path = ANALYSIS_DIR / "gps_data.csv"

    df = pd.read_csv(csv_path)

    required = [
        "timestamp",
        "altitude_msl_m",
        "vel_m_s"
    ]

    for column in required:
        if column not in df.columns:
            raise ValueError(
                f"Missing GPS column: {column}"
            )

    df["time_seconds"] = (
        df["timestamp"] / 1_000_000
    )

    fig, ax1 = plt.subplots(
        figsize=(12, 6)
    )

    ax1.plot(
        df["time_seconds"],
        df["altitude_msl_m"],
        linewidth=1
    )

    ax1.set_xlabel(
        "Time (seconds)"
    )

    ax1.set_ylabel(
        "Altitude MSL (m)"
    )

    ax1.grid(True)

    ax2 = ax1.twinx()

    ax2.plot(
        df["time_seconds"],
        df["vel_m_s"],
        linewidth=1
    )

    ax2.set_ylabel(
        "Ground Speed (m/s)"
    )

    plt.title(
        f"Altitude and Speed — {CASE_ID}"
    )

    plt.tight_layout()

    output = (
        OUTPUT_DIR
        / "altitude_speed_timeline.png"
    )

    plt.savefig(
        output,
        dpi=200
    )

    plt.close()

    print(f"Created: {output}")


# ============================================================
# 3. SECURITY EVENT TIMELINE
# ============================================================

def plot_security_timeline():

    security = load_json(
        "security_indicators.json"
    )

    indicators = security.get(
        "indicators",
        []
    )

    events = []

    for indicator in indicators:

        timestamp = indicator.get(
            "timestamp_seconds"
        )

        if timestamp is None:
            continue

        events.append({
            "time": timestamp,
            "type": indicator.get(
                "indicator_type",
                "UNKNOWN"
            ),
            "severity": indicator.get(
                "severity",
                "INFO"
            )
        })

    if not events:
        print(
            "No timestamped security indicators."
        )
        return

    events.sort(
        key=lambda x: x["time"]
    )

    plt.figure(
        figsize=(14, 7)
    )

    y_positions = list(
        range(len(events))
    )

    times = [
        event["time"]
        for event in events
    ]

    plt.scatter(
        times,
        y_positions,
        s=70
    )

    labels = [
        event["type"]
        for event in events
    ]

    plt.yticks(
        y_positions,
        labels
    )

    plt.xlabel(
        "Time from log start (seconds)"
    )

    plt.title(
        f"Security Indicator Timeline — {CASE_ID}"
    )

    plt.grid(
        axis="x"
    )

    plt.tight_layout()

    output = (
        OUTPUT_DIR
        / "security_indicator_timeline.png"
    )

    plt.savefig(
        output,
        dpi=200
    )

    plt.close()

    print(f"Created: {output}")


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("PX4 FORENSIC VISUALIZATION")
    print("=" * 70)
    print()

    plot_gps_path()

    plot_altitude_speed()

    plot_security_timeline()

    print()
    print(
        f"Output directory: {OUTPUT_DIR}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()
