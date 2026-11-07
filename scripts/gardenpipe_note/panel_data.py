"""Write the panel data from the generated data: three stations per date, in one shared file and one file each.

    python panel_data.py --source DIR --data DIR --days DAYS

Each row of a date goes to the next station in turn, so each station has a third of the rows, and the
shared file holds the same timestamps and values as the single stream it came from. The files are written
by streaming, so a large date does not have to fit in memory, but run this on its own all the same: peak
RSS is a high-water mark for the life of the process.
"""

import argparse
from pathlib import Path

import polars as pl
from gardenpipe.data import expand_dates

LABELS = ("A", "B", "C")
ROW_GROUP = 122_880  # what the generated files have, which is the Polars default

ap = argparse.ArgumentParser()
ap.add_argument("--source", type=Path, required=True)
ap.add_argument("--data", type=Path, required=True)
ap.add_argument("--days", type=int, required=True)
a = ap.parse_args()

a.data.mkdir(parents=True, exist_ok=True)
for day in expand_dates("20260105-20271231")[: a.days]:
    shared = a.data / f"panel_{day}.parquet"
    if shared.exists():
        continue
    rows = pl.scan_parquet(a.source / f"sensor_{day}.parquet").with_row_index("turn")
    turn = pl.col("turn") % len(LABELS)
    rows = rows.with_columns(
        station=pl.when(turn == 0).then(pl.lit(LABELS[0])).when(turn == 1).then(pl.lit(LABELS[1])).otherwise(pl.lit(LABELS[2]))
    ).drop("turn")
    for label in LABELS:
        rows.filter(pl.col("station") == label).select("time", "level").sink_parquet(
            a.data / f"{label}_{day}.parquet", row_group_size=ROW_GROUP
        )
    partial = shared.with_suffix(".partial")
    rows.sink_parquet(partial, row_group_size=ROW_GROUP)
    partial.rename(shared)
print(f"{a.data.name}: {a.days} dates, {sum(p.stat().st_size for p in a.data.glob('panel_*.parquet')) / 2**20:,.0f} MiB shared, "
      f"{sum(p.stat().st_size for p in a.data.glob('[ABC]_*.parquet')) / 2**20:,.0f} MiB in one file each")
