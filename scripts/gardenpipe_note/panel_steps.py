"""Where one date's memory goes in MultiSourceLoader: RSS and peak at each step.

    PYTHONPATH=CHECKOUT python panel_steps.py DATA_DIR ROWS_PER_DATE HORIZON shared|each

Each step's peak is read from VmHWM, which clear_refs resets between steps. This is one date in one
process, with no prefetch, so it shows which step is largest and not the peak of a whole run.
"""

import sys
import time
from pathlib import Path

import polars as pl
from gardenpipe.data import FeatureLoader, LoadHint, MultiSourceLoader
from gardenpipe.features import EwmaFeature

data, rows, horizon, files = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4]
day = "2026-01-05"
batch = 100_000


def rss():
    return int(open("/proc/self/statm").read().split()[1]) * 4096 / 2**20


def hwm():
    return next(int(line.split()[1]) for line in open("/proc/self/status") if line.startswith("VmHWM")) / 1024


def reset():
    open("/proc/self/clear_refs", "w").write("5")


started = [time.perf_counter()]


def mark(step):
    print(f"{step:32s} peak {hwm():7,.0f} MiB   end {rss():7,.0f} MiB   {time.perf_counter() - started[0]:7.1f} s", flush=True)
    reset()
    started[0] = time.perf_counter()


template = "panel_{date}.parquet" if files == "shared" else "{source}_{date}.parquet"
base = FeatureLoader(
    path=f"{data}/{template}",
    feature_exprs={"level": pl.col("level")},
    stateful_features=(EwmaFeature("level_ewm_1m", pl.col("level"), half_life="1m"),),
    targets={"forward_change": pl.col("level")},
    horizons=horizon,
)
loader = MultiSourceLoader(
    ["A", "B", "C"],
    base,
    label_col="station" if files == "shared" else None,
    tick_col="tick",
    feature_exprs={"difference": pl.col("a__level") - pl.col("b__level")},
)
print(f"{files}, {rows:,} rows, horizon {horizon}, polars {pl.__version__}")
hint = LoadHint(batch_size=batch)
mark("imports")
date = loader._open(day, hint)
mark("open the date")
ends = loader._window_ends(date, batch, "streaming")
mark(f"window ends ({len(ends)})")
prev, carry = None, None
for end in ends:
    outs = loader._window_outs(date, prev, end, "streaming", None)
    prev = end
    frame, carry = loader._join(loader._frames(date, outs), carry)
mark("every window, read and joined")
