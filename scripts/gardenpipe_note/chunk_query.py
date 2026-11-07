"""What one chunk of times costs: python chunk_query.py FILE, from a GardenPipe checkout.

time-chunks.patch reads the times of a date as one query per chunk. This prints the plans for select-then-slice and
slice-then-select, the time of one chunk at three offsets of FILE with a fresh scan each time, as the patch does, and
the same in memory. There the column is cast to ms and us first, so that the expression has real work to do, and a
slice that was not pushed down would show.
"""

import sys
import time

import polars as pl
from gardenpipe.data import _epoch_ns

B = 100_000
expr = _epoch_ns("time").alias("t")
path = sys.argv[1]


def median_ms(run, repeats=21):
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        run()
        times.append(time.perf_counter() - start)
    return sorted(times)[repeats // 2] * 1000


def orders(make, offset):
    """One chunk, select then slice and slice then select, in ms. Both must return the same rows."""
    first = lambda: make().select(expr).slice(offset, B).collect(engine="streaming")
    second = lambda: make().slice(offset, B).select(expr).collect(engine="streaming")
    assert first().equals(second())
    return median_ms(first), median_ms(second)


scan = lambda: pl.scan_parquet(path)
rows = scan().select(pl.len()).collect().item()
print(f"threads {pl.thread_pool_size()}, polars {pl.__version__}, file of {rows:,} rows")
print("plan, select then slice:", scan().select(expr).slice(rows // 2, B).explain(), sep="\n")
print("plan, slice then select:", scan().slice(rows // 2, B).select(expr).explain(), sep="\n")
print(f"collect_schema on a fresh scan: {median_ms(lambda: scan().collect_schema()):.2f} ms")
for offset in (0, rows // 2, rows - 2 * B):
    a, b = orders(scan, offset)
    print(f"Parquet, offset {offset:>11,}: select then slice {a:7.2f} ms, slice then select {b:7.2f} ms")
for unit in ("ms", "us"):
    frame = pl.read_parquet(path, columns=["time"]).with_columns(pl.col("time").cast(pl.Datetime(unit)))
    whole = median_ms(lambda: frame.lazy().select(expr).collect(engine="streaming"), 7)
    a, b = orders(frame.lazy, rows // 2)
    print(f"In memory, {unit}: whole column {whole:8.2f} ms, select then slice {a:6.3f} ms, slice then select {b:6.3f} ms")
