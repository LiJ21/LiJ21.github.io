"""Print the memory results as Markdown tables, in the form RESULTS.md uses: python summarize.py WORK_DIR

Reads every results*.jsonl in WORK_DIR, rff.jsonl if present, and the traces in WORK_DIR/rss.
"""

import csv
import json
import sys
from pathlib import Path


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.startswith("{")]


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


def one(tag, **match):
    rows = tagged(tag, **match)
    return rows[-1] if rows else None


def cell(record):
    return (mib(record["peak_rss_mib"]), seconds(record["seconds"])) if record else ("–", "–")


def millions(record):
    return f'{record["rows"] / 1e6:.0f}M'


sizes = sorted({r["rows"] for r in tagged("reader")})
table(
    "Polars alone on one file, no GardenPipe",
    ["Rows in the file", "Whole-column max, peak MiB", "Held-open stream, peak MiB", "Stream time, s", "Other CPU, s"],
    [
        (f"{size / 1e6:.0f}M", mib(one("reader", rows=size, query="max")["peak_rss_mib"]), *cell(one("reader", rows=size, query="stream")), other(one("reader", rows=size, query="stream")))
        for size in sizes
    ],
)
limited_read = one("reader-prefetch-8")
if limited_read:
    print(f'\nWith POLARS_ROW_GROUP_PREFETCH_SIZE=8, the stream over the {millions(limited_read)} file peaks at {mib(limited_read["peak_rss_mib"])} MiB.')

changes = (
    ("Nothing", "mech-base"),
    ("No model: batches are pulled and dropped", "mech-no-model"),
    ("Allocator returns freed memory at once", "mech-no-decay"),
    ("Read-ahead of 8 row groups", "mech-prefetch-8"),
    ("4 Polars threads", "mech-threads-4"),
    ("4 threads, read-ahead of 8", "combined-t4-p8"),
    ("4 threads, read-ahead of 8, immediate return", "combined-t4-p8-d0"),
)
table(
    "One change at a time: five dates, 100,000-row batches, 64 MiB budget, two workers",
    ["Change", "Peak at 4M, MiB", "Time at 4M, s", "Peak at 20M, MiB", "Time at 20M, s"],
    [(label, *cell(one(tag, rows=4_000_000)), *cell(one(tag, rows=20_000_000))) for label, tag in changes if one(tag)],
)

rows = sorted(tagged("density5") + tagged("mech-base"), key=lambda r: r["rows"])
table(
    "Rows per date: five dates, 100,000-row batches, 64 MiB budget, two workers",
    ["Rows per date", "Look-ahead rows", "Row groups", "Peak RSS, MiB", "Peak anonymous, MiB", "Time, s", "Other CPU, s"],
    [
        (millions(r), f'{r["rows"] * 300 // 86_400:,}', f'{-(-r["rows"] // 122_880):,}', mib(r["peak_rss_mib"]), split(f'density5_{r["rows"] // 1_000_000}m.csv')[0], seconds(r["seconds"]), other(r))
        for r in rows
    ],
)


def horizon_seconds(text):
    return int(text[:-1]) * {"s": 1, "m": 60, "h": 3600}[text[-1]]


rows = sorted(tagged("lookahead") + tagged("density5") + tagged("mech-base"), key=lambda r: (r["rows"], horizon_seconds(r.get("horizon", "5m"))))
table(
    "Look-ahead: five dates, default settings",
    ["Rows per date", "Horizon", "Look-ahead rows", "Peak RSS, MiB", "Time, s", "Other CPU, s"],
    [
        (millions(r), r.get("horizon", "5m"), f'{r["rows"] * horizon_seconds(r.get("horizon", "5m")) // 86_400:,}', mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r))
        for r in rows
    ],
)

base = one("mech-base", rows=4_000_000)
rows = tagged("threads") + ([base] if base else [])
table(
    "Polars threads: 20M rows over five dates",
    ["POLARS_MAX_THREADS", "Peak, MiB", "Time, s", "Other CPU, s"],
    [(r["settings"].get("POLARS_MAX_THREADS", "20 (default)"), mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r)) for r in rows],
)
table(
    "Warm files with and without deferred reads: 20M rows over five dates",
    ["Files", "Deferred reads", "Peak, MiB", "Time, s", "Other CPU, s"],
    [
        (state, setting, *cell(record), other(record) if record else "–")
        for state, setting, record in (
            ("Cold", "on", base),
            ("Warm", "on", one("warm")),
            ("Warm", "off", one("warm-no-defer")),
        )
        if record
    ],
)
table(
    "A slow consumer: 300 ms per training batch, no model, 20M rows over five dates",
    ["Budget, MiB", "Peak, MiB", "Time, s", "Other CPU, s"],
    [(f'{r["buffer_mib"]:,.0f}', mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r)) for r in tagged("slow-consumer")],
)
table(
    "Gradient boosting that finished under the 2 GiB limit: 40M rows",
    ["Mode", "Peak RSS, MiB", "Peak anonymous, MiB", "Peak file-backed, MiB", "Time, s", "Other CPU, s"],
    [
        (r["mode"], mib(r["peak_rss_mib"]), *split("xgb_2g_ext.csv" if r["mode"] == "external" else "xgb_2g_core.csv"), seconds(r["seconds"]), other(r))
        for r in tagged("xgb-2g")
    ],
)



def gap(after, before):
    """The largest change in any fitted coefficient, and the change in test R²."""
    if not after or not before:
        return "–", "–"
    return (
        f'{max(abs(x - y) for x, y in zip(after["coef"], before["coef"])):.1e}',
        f'{abs(after["test_r2"] - before["test_r2"]):.1e}',
    )


pinned = {r["rows"]: r for r in tagged("density5") + tagged("mech-base")}
filtered = {r["rows"]: r for r in tagged("fix-curve")}
both = {r["rows"]: r for r in tagged("chunk-curve")}
table(
    "What each patch changes: five dates, a five-minute horizon, default settings",
    ["Rows per date", "Look-ahead rows", "Pinned, MiB", "Window filter, MiB", "Both patches, MiB", "Pinned, s", "Window filter, s", "Both patches, s", "Largest coefficient change", "R² change"],
    [
        (
            f"{size / 1e6:.0f}M",
            f"{size * 300 // 86_400:,}",
            *(mib(group[size]["peak_rss_mib"]) if size in group else "–" for group in (pinned, filtered, both)),
            *(seconds(group[size]["seconds"]) if size in group else "–" for group in (pinned, filtered, both)),
            *gap(both.get(size), pinned.get(size)),
        )
        for size in sorted(both)
    ],
)
stream = {r["rows"]: r for r in tagged("lookahead") if r.get("horizon") != "25m"}
if 4_000_000 in pinned:
    stream[4_000_000] = pinned[4_000_000]
limited = {r["rows"]: r for r in tagged("fix-flat")}
chunks = {r["rows"]: r for r in tagged("chunk-flat")}
table(
    "The same look-ahead at every density: 13,888 rows, five dates",
    ["Rows per date", "Horizon", "Pinned, MiB", "Window filter and read-ahead of 8, MiB", "Both patches, MiB", "Pinned, s", "Both patches, s", "s per million rows, both patches"],
    [
        (
            f"{size / 1e6:.0f}M",
            r.get("horizon", "5m"),
            mib(stream[size]["peak_rss_mib"]) if size in stream else "–",
            mib(limited[size]["peak_rss_mib"]) if size in limited else "–",
            mib(r["peak_rss_mib"]),
            seconds(stream[size]["seconds"]) if size in stream else "–",
            seconds(r["seconds"]),
            f'{r["seconds"] / (r["rows"] * r["days"] / 1e6):.2f}',
        )
        for size, r in sorted(chunks.items())
    ],
)
table(
    "Polars alone, taking a batch of the time stream every 200 ms",
    ["Rows in the file", "Bare column, MiB", "Bare column, read-ahead of 8, MiB", "GardenPipe's expression, MiB", "Expression, read-ahead of 8, MiB"],
    [
        (
            f"{size / 1e6:.0f}M",
            *(mib(one(tag, rows=size)["peak_rss_mib"]) if one(tag, rows=size) else "–" for tag in ("slow-stream", "slow-stream-p8", "slow-epoch", "slow-epoch-p8")),
        )
        for size in sorted({r["rows"] for r in tagged("slow-stream")})
    ],
)
def peak_at_40m(tag):
    record = one(tag, rows=40_000_000)
    return mib(record["peak_rss_mib"]) if record else "–"


if one("slow-epoch-t4"):
    table(
        "The same stream at 40M rows, by Polars threads",
        ["POLARS_MAX_THREADS", "Bare column, MiB", "Bare column, read-ahead of 8, MiB", "GardenPipe's expression, MiB", "Expression, read-ahead of 8, MiB"],
        [
            ("20 (default)", *(peak_at_40m(tag) for tag in ("slow-stream", "slow-stream-p8", "slow-epoch", "slow-epoch-p8"))),
            ("4", *(peak_at_40m(tag) for tag in ("slow-stream-t4", "slow-stream-t4-p8", "slow-epoch-t4", "slow-epoch-t4-p8"))),
        ],
    )
base = both.get(4_000_000)
rows = tagged("chunk-threads", rows=4_000_000) + ([base] if base else [])
table(
    "Polars threads with both patches: 20M rows over five dates",
    ["POLARS_MAX_THREADS", "Peak, MiB", "Time, s", "Other CPU, s"],
    [(r["settings"].get("POLARS_MAX_THREADS", "20 (default)"), mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r)) for r in rows],
)
changes = (
    ("Nothing", "chunk-curve"),
    ("No model: batches are pulled and dropped", "chunk-no-model"),
    ("Allocator returns freed memory at once", "chunk-no-decay"),
    ("4 threads and immediate return", "chunk-t4-d0"),
)
table(
    "One change at a time with both patches: five dates",
    ["Change", "Peak at 4M, MiB", "Time at 4M, s", "Peak at 20M, MiB", "Time at 20M, s"],
    [(label, *cell(one(tag, rows=4_000_000)), *cell(one(tag, rows=20_000_000))) for label, tag in changes if one(tag)],
)
table(
    "A slow consumer with both patches: 300 ms per training batch, no model, 20M rows over five dates",
    ["Budget, MiB", "Peak, MiB", "Time, s", "Other CPU, s"],
    [(f'{r["buffer_mib"]:,.0f}', mib(r["peak_rss_mib"]), seconds(r["seconds"]), other(r)) for r in tagged("chunk-slow-consumer")],
)
table(
    "80M rows per date under the 1 GiB limit: five dates, a five-minute horizon",
    ["Loader", "Peak RSS, MiB", "Peak anonymous, MiB", "Peak file-backed, MiB", "Time, s", "Other CPU, s"],
    [
        (name, mib(r["peak_rss_mib"]), *split(f"limit80_{name}.csv"), seconds(r["seconds"]), other(r))
        for name in ("pinned", "patched")
        for r in tagged(f"limit80-{name}")
    ],
)

rows = tagged("rotation")
LOADERS = (
    ("Published", "7c64551632de"),
    ("Window filter", "3eb3b1aaf173"),
    ("Both patches", "be906867b2f2"),
    ("Both, a million times per query", "278db29cd861"),
)
table(
    "The same job from each checkout in rotation: 40M rows, ten dates",
    ["Mode", "Loader", "Runs", "Mean time, s", "Fastest and slowest, s", "Lowest and highest peak, MiB"],
    [
        (
            mode,
            name,
            len(same),
            seconds(sum(r["seconds"] for r in same) / len(same)),
            f'{seconds(min(r["seconds"] for r in same))}, {seconds(max(r["seconds"] for r in same))}',
            f'{mib(min(r["peak_rss_mib"] for r in same))}, {mib(max(r["peak_rss_mib"] for r in same))}',
        )
        for mode in ("materialize", "stream")
        for name, sha in LOADERS
        for same in [[r for r in rows if r["mode"] == mode and r.get("loader_sha") == sha]]
        if same
    ],
)
wide = {r["horizon"]: r for r in tagged("chunk-wide")}
table(
    "A million times per query at 80M rows per date: five dates",
    ["Horizon", "Look-ahead rows", "Both patches, MiB", "A million times per query, MiB", "Both patches, s", "A million times per query, s"],
    [
        (horizon, f"{look:,}", mib(same["peak_rss_mib"]), mib(wide[horizon]["peak_rss_mib"]), seconds(same["seconds"]), seconds(wide[horizon]["seconds"]))
        for horizon, look, same in (("15s", 13_888, chunks.get(80_000_000)), ("5m", 277_777, both.get(80_000_000)))
        if same and horizon in wide
    ],
)
rows = tagged("chunk-repeat")
table(
    "Ten dates repeated with both patches: three runs at each size",
    ["Rows per date", "Peak of each run, MiB", "Spread, MiB", "Mean time, s"],
    [
        (
            f"{size / 1e6:.0f}M",
            ", ".join(mib(r["peak_rss_mib"]) for r in same),
            mib(max(r["peak_rss_mib"] for r in same) - min(r["peak_rss_mib"] for r in same)),
            seconds(sum(r["seconds"] for r in same) / len(same)),
        )
        for size in sorted({r["rows"] for r in rows})
        for same in [[r for r in rows if r["rows"] == size]]
    ],
)
table(
    "The billion-row job repeated with both patches, under the 1 GiB limit",
    ["Rows", "Peak RSS, MiB", "Peak anonymous, MiB", "Peak file-backed, MiB", "Time, s", "Other CPU, s"],
    [(f'{r["total_rows"] / 1e6:,.0f}M', mib(r["peak_rss_mib"]), *split("chunk_billion.csv"), seconds(r["seconds"]), other(r)) for r in tagged("chunk-billion")],
)
table(
    "Gradient boosting that finished under the 2 GiB limit with both patches: 40M rows",
    ["Mode", "Peak RSS, MiB", "Peak anonymous, MiB", "Peak file-backed, MiB", "Time, s", "Other CPU, s"],
    [
        (r["mode"], mib(r["peak_rss_mib"]), *split("chunk_xgb_2g_ext.csv" if r["mode"] == "external" else "chunk_xgb_2g_core.csv"), seconds(r["seconds"]), other(r))
        for r in tagged("chunk-xgb-2g")
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
