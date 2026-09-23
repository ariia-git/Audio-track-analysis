from __future__ import annotations
import csv
from pathlib import Path
import numpy as np
from .utils import timestamp, write_json

def energy_rows(features: dict, sections: list, interval: float, duration: float, stable: float):
    """Aggregate into user-facing intervals instead of point sampling away transients."""
    t = features["timestamp_seconds"]
    section_index = 0
    for start in np.arange(0, duration, interval):
        end = min(start+interval, duration)
        lo, hi = np.searchsorted(t, [start, end])
        lo = min(lo, len(t)-1)
        hi = max(lo+1, hi)
        row = {"timestamp_seconds": round(float(start), 6), "timestamp": timestamp(float(start))}
        for key, values in features.items():
            if key != "timestamp_seconds":
                row[key] = round(float(np.mean(values[lo:hi])), 7)
        while section_index < len(sections)-1 and start >= sections[section_index]["end"]:
            section_index += 1
        row["phase"] = sections[section_index]["phase"]
        row["energy_direction"] = "rising" if row["energy_delta"] > stable else "falling" if row["energy_delta"] < -stable else "stable"
        yield row

def save_energy(folder: Path, features: dict, sections: list, config: dict, duration: float) -> int:
    import json
    count = 0
    # Stream both formats without building a second full set of row dictionaries.
    with (folder / "energy.csv").open("w", newline="", encoding="utf-8") as csv_file, (folder / "energy.json").open("w", encoding="utf-8") as json_file:
        writer = None
        json_file.write("[\n")
        for row in energy_rows(features, sections, config["interval"], duration, config["energy"]["stable_delta"]):
            if writer is None:
                writer = csv.DictWriter(csv_file, fieldnames=list(row))
                writer.writeheader()
            writer.writerow(row)
            if count:
                json_file.write(",\n")
            json.dump(row, json_file, allow_nan=False)
            count += 1
        json_file.write("\n]\n")
    return count
