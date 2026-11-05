"""What the station recorded around the worst forecast of the test years. Run from a GardenPipe checkout."""

from datetime import datetime

import polars as pl

frame = pl.read_parquet("data/jena/jena_2015.parquet").sort("time")
window = frame.filter(pl.col("time").is_between(datetime(2015, 6, 1, 4), datetime(2015, 6, 1, 14)), pl.col("time").dt.minute() == 0)
print(window.select("time", "T", "p", "rh", "wv", "wd"))
