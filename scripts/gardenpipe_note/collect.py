"""Gather experiment results into data/gardenpipe-note.json for the figures.

    python collect.py PATCHED_DIR PUBLISHED_DIR
PATCHED_DIR holds the grids run with both patches: results*.jsonl, rss/, and the CSV files from figure_data.py.
PUBLISHED_DIR holds results_followup.jsonl, whose curves the rows-per-date figure draws.
"""

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
work, published = Path(sys.argv[1]), Path(sys.argv[2])


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.startswith("{")]


records = [record for path in sorted(work.glob("results*.jsonl")) for record in load(path)] + load(published / "results_followup.jsonl")


def trace(name, points=240):
    rows = [(float(r["t"]), float(r["rss_mib"]) / 1024) for r in csv.DictReader((work / "rss" / name).open())]
    step = max(1, len(rows) // points)
    kept = rows[::step]
    return [[round(t, 1), round(v, 3)] for t, v in (kept if kept[-1] == rows[-1] else [*kept, rows[-1]])]


def week(name, start):
    origin = datetime.fromisoformat(start)
    out = []
    for r in csv.DictReader((work / f"week_{name}.csv").open()):
        t = datetime.fromisoformat(r["target_time"])
        out.append([round((t - origin).total_seconds() / 86400, 4), float(r["T_observed"]), float(r["pred_history"]), float(r["pred_persistence"])])
    return out


def bias(name):
    rows = csv.DictReader((work / f"heat_{name}.csv").open())
    return sorted([int(r["mo"]), int(r["h"]), round(float(r["b"]), 3)] for r in rows)


scale = [
    {
        "mode": r["mode"],
        "rows_m": r["total_rows"] / 1e6,
        "peak_gib": round(r["peak_rss_mib"] / 1024, 3),
        "seconds": round(r["seconds"], 1),
        "disk_gib": round(r["disk_mib"] / 1024, 3),
        "r2": r["test_r2"],
    }
    for r in records
    if r["tag"] == "scale"
]
def size(mib):
    return f"{mib * 1024:.1f} KiB" if mib < 1 else f"{mib:.0f} MiB"


def curve(*tags):
    """Peak against rows per date, from the five-date runs with these tags."""
    return sorted([r["rows"] / 1e6, round(r["peak_rss_mib"])] for r in records if r["tag"] in tags)


cap_stream, cap_mat = trace("cap_stream.csv"), trace("cap_mat.csv")
out = {
    "scale": sorted(scale, key=lambda r: (r["mode"], r["rows_m"])),
    "density": {
        "first": curve("density5", "mech-base"),
        "fixed": curve("chunk-curve"),
        "same_lookahead": curve("chunk-flat"),
    },
    "cap": {"stream": cap_stream, "materialize": cap_mat, "killed_after": cap_mat[-1][0]},
    "weeks": {"winter": week("winter", "2015-01-12"), "summer": week("summer", "2015-07-13")},
    "bias": {"ridge": bias("ridge"), "boosting": bias("xgb")},
    "width": {
        "boosting": round(load(work / "boosting_weather.jsonl")[-1]["mae"], 4),
        "points": [
            {"d": r["d"], "mae": round(r["mae"], 4), "label": size(r["gram_mib"])}
            for r in sorted((r for r in load(work / "rff.jsonl") if r["seed"] == 0), key=lambda r: r["d"])
        ],
    },
}
(ROOT / "data/gardenpipe-note.json").write_text(json.dumps(out, separators=(",", ":")) + "\n")
print({k: len(v) for k, v in out.items()})
