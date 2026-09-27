from pathlib import Path

from pyulog import ULog


def inventory_ulog(path):
    """
    Return a structural inventory of all datasets in a PX4 ULog.

    The sample count is determined from the timestamp field,
    rather than len(dataset.data), because dataset.data is a
    dictionary of fields.
    """

    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"ULog does not exist: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"ULog path is not a file: {path}"
        )

    ulog = ULog(str(path))

    inventory = []

    for dataset in ulog.data_list:
        data = dataset.data

        timestamp = data.get("timestamp")

        if timestamp is not None:
            sample_count = len(timestamp)
        elif data:
            first_field = next(iter(data.values()))
            sample_count = len(first_field)
        else:
            sample_count = 0

        inventory.append(
            {
                "name": dataset.name,
                "instance": getattr(
                    dataset,
                    "multi_id",
                    0,
                ),
                "sample_count": sample_count,
                "field_count": len(data),
                "fields": list(data.keys()),
            }
        )

    return inventory
