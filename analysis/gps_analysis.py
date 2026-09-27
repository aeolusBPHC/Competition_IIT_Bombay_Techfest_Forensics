from pathlib import Path
import json
import math


def load_gps_data(path):
    with open(path) as f:
        return json.load(f)


def analyze_gps(records):

    if not records:
        return {
            "sample_count": 0
        }

    latitudes = [
        r["latitude_deg"]
        for r in records
    ]

    longitudes = [
        r["longitude_deg"]
        for r in records
    ]

    altitudes = [
        r["altitude_msl_m"]
        for r in records
    ]

    speeds = [
        r["vel_m_s"]
        for r in records
    ]

    satellites = [
        r["satellites_used"]
        for r in records
    ]

    hdop = [
        r["hdop"]
        for r in records
    ]

    vdop = [
        r["vdop"]
        for r in records
    ]

    fix_types = [
        r["fix_type"]
        for r in records
    ]

    return {

        "sample_count": len(records),

        "latitude": {
            "min": min(latitudes),
            "max": max(latitudes)
        },

        "longitude": {
            "min": min(longitudes),
            "max": max(longitudes)
        },

        "altitude_msl_m": {
            "min": min(altitudes),
            "max": max(altitudes)
        },

        "speed_m_s": {
            "min": min(speeds),
            "max": max(speeds),
            "average": sum(speeds) / len(speeds)
        },

        "satellites": {
            "min": min(satellites),
            "max": max(satellites),
            "average": sum(satellites) / len(satellites)
        },

        "hdop": {
            "min": min(hdop),
            "max": max(hdop),
            "average": sum(hdop) / len(hdop)
        },

        "vdop": {
            "min": min(vdop),
            "max": max(vdop),
            "average": sum(vdop) / len(vdop)
        },

        "fix_types_observed": sorted(
            set(fix_types)
        )
    }


if __name__ == "__main__":

    gps_file = Path(
        "repository/cases/"
        "CASE-001/"
        "EVD-20260919-175126/"
        "analysis/"
        "gps_data.json"
    )

    records = load_gps_data(gps_file)

    summary = analyze_gps(records)

    print("=" * 70)
    print("GPS FORENSIC ANALYSIS")
    print("=" * 70)

    print(json.dumps(
        summary,
        indent=4
    ))
