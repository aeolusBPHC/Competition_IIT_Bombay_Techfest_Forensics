from pathlib import Path
from pyulog import ULog
import csv
import json


class GPSExtractor:
    """
    Extract forensic GPS information from a PX4 ULog.
    """

    def __init__(self, log_path):
        self.log_path = Path(log_path)

        if not self.log_path.exists():
            raise FileNotFoundError(
                f"ULog not found: {self.log_path}"
            )

        self.ulog = ULog(str(self.log_path))

        datasets = [
            d for d in self.ulog.data_list
            if d.name == "vehicle_gps_position"
        ]

        if not datasets:
            raise ValueError(
                "vehicle_gps_position dataset not found"
            )

        self.data = datasets[0].data

    def extract(self):
        """
        Extract important GPS fields into a list of records.
        """

        fields = [
            "timestamp",
            "latitude_deg",
            "longitude_deg",
            "altitude_msl_m",
            "altitude_ellipsoid_m",
            "vel_m_s",
            "vel_n_m_s",
            "vel_e_m_s",
            "vel_d_m_s",
            "fix_type",
            "satellites_used",
            "hdop",
            "vdop",
            "eph",
            "epv",
            "jamming_indicator",
            "jamming_state",
            "spoofing_state",
            "authentication_state",
            "vel_ned_valid"
        ]

        available_fields = [
            field for field in fields
            if field in self.data
        ]

        number_of_samples = len(
            self.data[available_fields[0]]
        )

        records = []

        for i in range(number_of_samples):

            record = {}

            for field in available_fields:
                value = self.data[field][i]

                # Convert NumPy scalar values into
                # normal Python values for JSON/CSV.
                if hasattr(value, "item"):
                    value = value.item()

                record[field] = value

            records.append(record)

        return records

    def export_csv(self, records, output_path):

        output_path = Path(output_path)
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        if not records:
            return

        with open(
            output_path,
            "w",
            newline=""
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=records[0].keys()
            )

            writer.writeheader()
            writer.writerows(records)

    def export_json(self, records, output_path):

        output_path = Path(output_path)
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(output_path, "w") as f:
            json.dump(
                records,
                f,
                indent=2
            )


if __name__ == "__main__":

    log_path = (
        "repository/cases/"
        "CASE-001/"
        "EVD-20260919-175126/"
        "evidence/"
        "17_02_27.ulg"
    )

    output_directory = Path(
        "repository/cases/"
        "CASE-001/"
        "EVD-20260919-175126/"
        "analysis"
    )

    extractor = GPSExtractor(log_path)

    records = extractor.extract()

    csv_path = output_directory / "gps_data.csv"
    json_path = output_directory / "gps_data.json"

    extractor.export_csv(
        records,
        csv_path
    )

    extractor.export_json(
        records,
        json_path
    )

    print("=" * 70)
    print("PX4 GPS FORENSIC EXTRACTION")
    print("=" * 70)

    print(f"\nEvidence file:")
    print(log_path)

    print(f"\nGPS samples:")
    print(len(records))

    print(f"\nCSV:")
    print(csv_path)

    print(f"\nJSON:")
    print(json_path)

    if records:

        print("\nFirst GPS record:")
        print(json.dumps(
            records[0],
            indent=2
        ))

        print("\nLast GPS record:")
        print(json.dumps(
            records[-1],
            indent=2
        ))
