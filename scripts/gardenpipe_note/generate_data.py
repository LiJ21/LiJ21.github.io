"""Write the generated dataset, one Parquet file per date.

    python generate_data.py --data DIR --rows ROWS_PER_DATE --days DAYS

Run this on its own, never inside a measured process: writing a date holds that whole date in memory,
and peak RSS is a high-water mark for the life of the process. Files that exist are kept. Each file is
a pure function of its row count and its position in the date list.
"""

import argparse
import datetime as dt
import hashlib
from pathlib import Path

import numpy as np
import polars as pl
from gardenpipe.data import expand_dates

ap = argparse.ArgumentParser()
ap.add_argument("--data", type=Path, required=True)
ap.add_argument("--rows", type=int, required=True)
ap.add_argument("--days", type=int, required=True)
a = ap.parse_args()


def write_day(path, day, rows, seed):
    rng = np.random.default_rng(seed)
    noise = pl.Series(rng.normal(size=rows))
    level = noise.ewm_mean(alpha=0.005, adjust=False) / 0.005
    start = dt.datetime.fromisoformat(day)
    step = dt.timedelta(seconds=86_400 / rows)
    pl.DataFrame(
        {
            "time": pl.datetime_range(
                start, start + step * (rows - 1), step, eager=True, time_unit="ns"
            ),
            "level": level,
        }
    ).write_parquet(path)


dates = expand_dates("20260105-20271231")[: a.days]
assert len(dates) == a.days, len(dates)
a.data.mkdir(parents=True, exist_ok=True)
for i, day in enumerate(dates):
    path = a.data / f"sensor_{day}.parquet"
    if not path.exists():
        partial = path.with_suffix(".partial")
        write_day(partial, day, a.rows, seed=i)
        partial.rename(path)
digest = hashlib.sha256((a.data / f"sensor_{dates[0]}.parquet").read_bytes()).hexdigest()
print(f"{a.data.name}: {a.rows} rows, {a.days} dates, first file sha256 {digest}")
