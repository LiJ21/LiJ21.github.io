"""Print the memory results as Markdown tables, in the form RESULTS.md uses: python summarize.py WORK_DIR

Reads every results*.jsonl in WORK_DIR, rff.jsonl if present, and the traces in WORK_DIR/rss.
"""

import csv
import json
import sys
from pathlib import Path


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


work = Path(sys.argv[1])
records = [record for path in sorted(work.glob("results*.jsonl")) for record in load(path)]


def tagged(tag, **match):
    return [r for r in records if r["tag"] == tag and all(r.get(k) == v for k, v in match.items())]


def table(title, header, lines):
    if not lines:
        return
    print(f"\n**{title}**\n")
    print("| " + " | ".join(header) + " |")
    print("| " + " | ".join(["---"] + ["---:"] * (len(header) - 1)) + " |")
    for line in lines:
        print("| " + " | ".join(str(cell) for cell in line) + " |")


def mib(value):
    return f"{value:,.0f}"


def seconds(value):
    return f"{value:,.1f}"


def other(record):
    return record.get("other_cpu_seconds", "–")


def split(name):
    """Peak anonymous and file-backed RSS from a trace; the two peaks need not coincide."""
    path = work / "rss" / name
    if not path.exists():
        return "–", "–"
    rows = list(csv.DictReader(path.open()))
    if not rows or "anon_mib" not in rows[0]:
        return "–", "–"
    return mib(max(float(r["anon_mib"]) for r in rows)), mib(max(float(r["file_mib"]) for r in rows))


def spread(rows):
    values = [r["test_r2"] for r in rows]
    return max(values) - min(values)


lines = []
for state in ("cold", "warm"):
    rows = tagged("cache", page_cache=state)
    if rows:
        peaks = [r["peak_rss_mib"] for r in rows]
        lines.append((state, len(rows), mib(min(peaks)), mib(max(peaks)), seconds(sum(r["seconds"] for r in rows) / len(rows)), f'{max(other(r) for r in rows)}'))
table(
    "Page cache: the same 40M-row job, files evicted or read first",
    ["Files", "Runs", "Lowest peak, MiB", "Highest peak, MiB", "Mean time, s", "Most other CPU, s"],
    lines,
)

lines = []
for days in sorted({r["days"] for r in tagged("scale")}):
    s = tagged("scale", days=days, mode="stream")[-1]
    m = tagged("scale", days=days, mode="materialize")[-1]
    lines.append(
        (
            f'{s["total_rows"] / 1e6:,.0f}M',
            days,
            mib(s["disk_mib"]),
            mib(s["peak_rss_mib"]),
            mib(m["peak_rss_mib"]),
            seconds(s["seconds"]),
            seconds(m["seconds"]),
            f'{s["seconds"] / m["seconds"]:.2f}',
            f'{abs(s["test_r2"] - m["test_r2"]):.1e}',
            f'{other(s)} / {other(m)}',
        )
    )
table(
    "Number of dates: 4M rows per date, 100,000-row batches, 64 MiB budget, two workers",
    ["Rows", "Dates", "Disk, MiB", "Streamed peak, MiB", "Materialized peak, MiB", "Streamed, s", "Materialized, s", "Time ratio", "R² gap", "Other CPU, s"],
    lines,
)
materialized = sorted(tagged("scale", mode="materialize"), key=lambda r: r["total_rows"])
if len(materialized) > 1:
    x = [r["total_rows"] / 1e6 for r in materialized]
    y = [r["peak_rss_mib"] for r in materialized]
    x_mean, y_mean = sum(x) / len(x), sum(y) / len(y)
    slope = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y)) / sum((a - x_mean) ** 2 for a in x)
    intercept = y_mean - slope * x_mean
    print(f"\nMaterialized fit: {slope:.1f} MiB per million rows ({slope * 100 / 1024:.2f} GiB per 100M), intercept {intercept:.0f} MiB, {(slope * 1000 + intercept) / 1024:.1f} GiB at one billion rows.")

table(
    "The same 30-day streamed job, repeated",
    ["Run", "Peak, MiB", "Time, s", "Other CPU, s"],
    [(r["tag"], mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r)) for r in records if r.get("days") == 30 and r.get("mode") == "stream" and r["tag"] in ("scale", "repeat", "trace", "cap")],
)

rows = tagged("batch")
table(
    "Batch size: 40M rows, two workers",
    ["Batch rows", "Budget, MiB", "Peak, MiB", "Time, s", "Other CPU, s"],
    [(f'{r["batch"]:,}', f'{r["buffer_mib"]:.0f}', mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r)) for r in rows],
)
if rows:
    print(f"\nSpread of test R² across batch sizes: {spread(rows):.1e}.")
rows = tagged("buffer")
table(
    "Prefetch budget: 40M rows, 100,000-row batches, two workers",
    ["Budget, MiB", "Peak, MiB", "Time, s", "Other CPU, s"],
    [(f'{r["buffer_mib"]:,.0f}', mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r)) for r in rows],
)
rows = tagged("workers")
table(
    "Workers: 40M rows, 100,000-row batches, 64 MiB budget",
    ["Workers", "Peak, MiB", "Time, s", "Other CPU, s"],
    [(r["workers"], mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r)) for r in rows],
)
table(
    "Rows per date: ten dates, 100,000-row batches, 64 MiB budget, two workers",
    ["Rows per date", "File, MiB", "Peak RSS, MiB", "Peak anonymous, MiB", "Peak file-backed, MiB", "Time, s", "Other CPU, s"],
    [
        (f'{r["rows"] / 1e6:.0f}M', mib(r["disk_mib"] / r["days"]), mib(r["peak_rss_mib"]), *split(f'density_{r["rows"] // 1_000_000}m.csv'), seconds(r["seconds"]), other(r))
        for r in sorted(tagged("density"), key=lambda r: r["rows"])
    ],
)
limited = [(r, "cap_stream.csv") for r in tagged("cap", mode="stream")] + [(r, "billion.csv") for r in tagged("billion")]
table(
    "Completed under the 1 GiB limit",
    ["Run", "Rows", "Disk, GiB", "Peak RSS, MiB", "Peak anonymous, MiB", "Peak file-backed, MiB", "Time, s", "Other CPU, s"],
    [(r["tag"], f'{r["total_rows"] / 1e6:,.0f}M', f'{r["disk_mib"] / 1024:.2f}', mib(r["peak_rss_mib"]), *split(name), seconds(r["seconds"]), other(r)) for r, name in limited],
)
table(
    "Gradient boosting on the generated data: 4M rows per date",
    ["Mode", "Rows", "Peak RSS, MiB", "Peak anonymous, MiB", "Peak file-backed, MiB", "Time, s", "Test R²", "Other CPU, s"],
    [
        (r["mode"], f'{r["total_rows"] / 1e6:,.0f}M', mib(r["peak_rss_mib"]), *(split(f'xgb_ext_{r["days"]}.csv') if r["mode"] == "external" else ("–", "–")), seconds(r["seconds"]), f'{r["test_r2"]:.6f}', other(r))
        for r in sorted(tagged("xgb"), key=lambda r: (r["days"], r["mode"]))
    ],
)
table(
    "Gradient boosting that finished under the 1 GiB limit: 40M rows",
    ["Mode", "Peak RSS, MiB", "Peak anonymous, MiB", "Peak file-backed, MiB", "Time, s", "Other CPU, s"],
    [
        (r["mode"], mib(r["peak_rss_mib"]), *split("xgb_cap_ext.csv" if r["mode"] == "external" else "xgb_cap_core.csv"), seconds(r["seconds"]), other(r))
        for r in tagged("xgb-cap")
    ],
)
path = work / "rff.jsonl"
if path.exists():
    table(
        "Ridge on random Fourier features, weather data",
        ["Random features", "Seed", "Inputs", "X′X, MiB", "α", "Test MAE, °C", "Test RMSE, °C", "Peak RSS, MiB", "Time, s", "Other CPU, s"],
        [
            (f'{r["D"]:,}', r["seed"], f'{r["d"]:,}', f'{r["gram_mib"]:.3g}', r["alpha"], f'{r["mae"]:.4f}', f'{r["rmse"]:.4f}', mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r))
            for r in sorted(load(path), key=lambda r: (r["D"], r["seed"]))
        ],
    )
