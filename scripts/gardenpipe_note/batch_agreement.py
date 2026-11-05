"""How far do the weather forecasts move with the batch size? python batch_agreement.py WORK_DIR"""

import sys

import polars as pl

work = sys.argv[1]
base = pl.read_parquet("runs/weather/predictions.parquet").sort("issue_time")
for batch in (5000, 1000000):
    other = pl.read_parquet(f"{work}/weather_{batch}/predictions.parquet").sort("issue_time")
    assert other["issue_time"].equals(base["issue_time"])
    for column in ("pred_calendar", "pred_history"):
        gap = (other[column] - base[column]).abs().max()
        print(f"batch {batch} against 20000, {column}: {other.height} forecasts, largest gap {gap:.3e} degrees C")
