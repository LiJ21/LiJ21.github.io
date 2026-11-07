"""Polars alone, with no GardenPipe: one query over one Parquet file, in a fresh process.

max scans the whole time column once, as GardenPipe does when it opens a date.
stream holds a time-only query open and takes its batches slowly, as GardenPipe does to cut a date into windows.
--column epoch selects the expression GardenPipe uses, instead of the bare column.
"""

import argparse
import json
import time
from pathlib import Path

import polars as pl

from run_record import Stopwatch

ap = argparse.ArgumentParser()
ap.add_argument("--file", type=Path, required=True)
ap.add_argument("--rows", type=int, required=True)
ap.add_argument("--query", choices=["max", "stream"], required=True)
ap.add_argument("--batch", type=int, default=100_000)
ap.add_argument("--pause-ms", type=float, default=20, help="time spent on each batch of the stream")
ap.add_argument("--column", choices=["bare", "epoch"], default="bare")
ap.add_argument("--tag", default="reader")
ap.add_argument("--page-cache", default="unknown")
ap.add_argument("--out", type=Path)
a = ap.parse_args()

scan = pl.scan_parquet(a.file)
clock = Stopwatch()
if a.query == "max":
    scan.select(pl.col("time").max()).collect(engine="streaming")
else:
    column = pl.col("time")
    if a.column == "epoch":
        column = column.cast(pl.Datetime("ns")).dt.epoch("ns").alias("t")
    for _ in scan.select(column).collect_batches(chunk_size=a.batch, maintain_order=True, engine="streaming"):
        time.sleep(a.pause_ms / 1000)
record = dict(tag=a.tag, query=a.query, column=a.column, pause_ms=a.pause_ms, rows=a.rows, page_cache=a.page_cache, **clock.record())
print(json.dumps(record))
if a.out:
    a.out.write_text(json.dumps(record) + "\n")
