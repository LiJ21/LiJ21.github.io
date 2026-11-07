"""Run the real windowed loader on each kind of time column and print a digest of every batch.

Two horizons, a file and a frame, both engines: 8 cases per column. The JSON it prints goes to
compare_column_types.py.

    PYTHONPATH=CHECKOUT python loader_column_types.py SCRATCH_DIR > polars-VERSION.CODE.json
"""
import hashlib, json, sys, tempfile, datetime as dt
from pathlib import Path
import numpy as np, polars as pl
from gardenpipe.data import FeatureLoader, LoadHint
import gardenpipe.data as gd

BASE = dt.datetime(2026, 1, 5)
ROWS = 5_000
STEP_NS = 1_000_000_000
rng = np.random.default_rng(7)
level = rng.normal(size=ROWS).cumsum()
t0 = int(BASE.replace(tzinfo=dt.timezone.utc).timestamp()) * 10**9
ns = t0 + np.arange(ROWS) * STEP_NS

def col(kind):
    s = pl.Series("time", ns, dtype=pl.Int64)
    d = s.cast(pl.Datetime("ns"))
    if kind.startswith("dt_"):
        unit = kind.split("_")[1]
        out = d.cast(pl.Datetime(unit))
        if len(kind.split("_")) > 2:
            tz = {"utc": "UTC", "ams": "Europe/Amsterdam"}[kind.split("_")[2]]
            out = out.dt.replace_time_zone("UTC").dt.convert_time_zone(tz)
        return out
    if kind == "int64_ns": return s
    if kind == "date": return d.dt.date().alias("time")
    if kind == "time_of_day": return d.dt.time().alias("time")
    if kind == "duration_ns": return (d - d.min()).alias("time")
    # Small clocks, as a tick counter would be: nanoseconds since the first row.
    small = pl.Series("time", np.arange(ROWS) * 1_000, dtype=pl.Int64)
    if kind == "int64_small": return small
    if kind == "int32_small": return small.cast(pl.Int32)
    if kind == "uint32_small": return small.cast(pl.UInt32)
    if kind == "uint64_ns": return s.cast(pl.UInt64)
    if kind == "float64_ns": return s.cast(pl.Float64)
    if kind == "float64_small": return small.cast(pl.Float64)
    if kind == "string_iso": return d.dt.to_string("%Y-%m-%dT%H:%M:%S%.f").alias("time")
    if kind == "string_space": return d.dt.to_string("%Y-%m-%d %H:%M:%S%.f").alias("time")
    raise KeyError(kind)

KINDS = ["dt_ns", "dt_us", "dt_ms", "dt_ns_utc", "dt_us_ams", "int64_ns", "uint64_ns", "int64_small",
         "int32_small", "uint32_small", "float64_ns", "float64_small", "string_iso", "string_space", "date", "time_of_day", "duration_ns"]
date = "20260105"
root = Path(tempfile.mkdtemp(dir=sys.argv[1]))
out = {}
for kind in KINDS:
    df = pl.DataFrame({"time": col(kind), "level": level})
    path = root / kind
    path.mkdir()
    df.write_parquet(path / f"sensor_{date}.parquet", row_group_size=500)
    for horizon in ("5s", "5m"):
        for source in ("file", "frame"):
            for engine in ("streaming", "in-memory"):
                args = dict(feature_exprs={"level": pl.col("level")}, targets={"y": pl.col("level")}, horizons=horizon)
                loader = (FeatureLoader(path=f"{path}/sensor_{{date}}.parquet", **args) if source == "file"
                          else FeatureLoader(frames={date: df}, **args))
                key = f"{kind}|{horizon}|{source}|{engine}"
                try:
                    h = hashlib.sha256(); rows = 0; batches = 0
                    for frame in loader.iter_date_frames([date], hint=LoadHint(batch_size=700, polars_engine=engine)):
                        b = frame.lf.collect()
                        rows += b.height; batches += 1
                        h.update(b.select(pl.all().cast(pl.String, strict=False)).write_csv().encode())
                    out[key] = f"{rows} rows {batches} batches {h.hexdigest()[:12]}"
                except Exception as e:
                    out[key] = f"ERROR {type(e).__name__}: {str(e).splitlines()[0][:70]}"
print(json.dumps(dict(polars=pl.__version__, data=hashlib.sha256(Path(gd.__file__).read_bytes()).hexdigest()[:12], out=out)))
