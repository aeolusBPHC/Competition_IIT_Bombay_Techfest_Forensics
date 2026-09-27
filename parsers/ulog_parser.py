from pathlib import Path
from pyulog import ULog


class PX4ULogParser:
    """
    Parser for PX4 ULog forensic evidence.

    The parser extracts high-value forensic information
    from the ULog without modifying the evidence file.
    """

    def __init__(self, log_path):
        self.log_path = Path(log_path)

        if not self.log_path.exists():
            raise FileNotFoundError(
                f"ULog file not found: {self.log_path}"
            )

        if not self.log_path.is_file():
            raise ValueError(
                f"ULog path is not a file: {self.log_path}"
            )

        self.ulog = ULog(str(self.log_path))

    def get_basic_information(self):
        """
        Return basic information about the ULog.
        """

        return {
            "file": str(self.log_path),
            "file_size_bytes": self.log_path.stat().st_size,
            "start_timestamp_us": self.ulog.start_timestamp,
            "end_timestamp_us": self.ulog.last_timestamp,
            "duration_seconds": (
                self.ulog.last_timestamp
                - self.ulog.start_timestamp
            ) / 1_000_000,
            "dataset_count": len(self.ulog.data_list),
        }

    def get_dataset_names(self):
        """
        Return all datasets contained in the ULog.
        """

        return [
            data.name
            for data in self.ulog.data_list
        ]

    def find_datasets(self, name):
        """
        Return all datasets matching a given name.

        Multiple instances can exist for the same topic.
        """

        return [
            data
            for data in self.ulog.data_list
            if data.name == name
        ]

    def get_dataset_fields(self, name):
        """
        Return fields available in a dataset.
        """

        datasets = self.find_datasets(name)

        result = []

        for data in datasets:
            result.append({
                "name": data.name,
                "multi_id": data.multi_id,
                "fields": list(data.data.keys())
            })

        return result


if __name__ == "__main__":

    path = (
        "repository/cases/"
        "CASE-001/"
        "EVD-20260919-175126/"
        "evidence/"
        "17_02_27.ulg"
    )

    parser = PX4ULogParser(path)

    print("=" * 70)
    print("PX4 DRONE FORENSIC PARSER")
    print("=" * 70)

    print("\nBasic information:")
    print(parser.get_basic_information())

    print("\nDataset count:")
    print(len(parser.get_dataset_names()))

    print("\nGPS datasets:")
    print(parser.get_dataset_fields(
        "vehicle_gps_position"
    ))

    print("\nVehicle status datasets:")
    print(parser.get_dataset_fields(
        "vehicle_status"
    ))

    print("\nGlobal position datasets:")
    print(parser.get_dataset_fields(
        "vehicle_global_position"
    ))
