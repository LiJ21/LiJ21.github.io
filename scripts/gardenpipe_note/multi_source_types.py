"""MultiSourceLoader on each kind of time column: a digest of every batch, to compare two checkouts.

    PYTHONPATH=CHECKOUT python multi_source_types.py SCRATCH_DIR > CODE.json
    python3 multi_source_types.py --compare BEFORE.json AFTER.json

Two horizons, one shared file and one file per station, wide and long, both engines: 16 cases per column.
"""
import hashlib, json, sys, tempfile, datetime as dt

if sys.argv[1] == "--compare":
    a, b = (json.load(open(path)) for path in sys.argv[2:4])
    print(f"polars {a['polars']}: {a['data']} against {b['data']}")
    kinds = {}
    for key, x in a["out"].items():
        kinds.setdefault(key.split("|")[0], []).append((key, x, b["out"][key]))
    for kind, cases in kinds.items():
        same = sum(x == y for _, x, y in cases)
        failed = sum(x.startswith("ERROR") for _, x, _ in cases)
        print(f"{kind:16s} {same:3d} of {len(cases)} identical, {failed} fail in both" if same == len(cases) and failed else f"{kind:16s} {same:3d} of {len(cases)} identical")
        for key, x, y in cases:
            if x != y:
                print(f"   {key}: {x} | {y}")
    print(sum(x == y for cases in kinds.values() for _, x, y in cases), "of", len(a["out"]), "identical")
    raise SystemExit

from pathlib import Path
import numpy as np, polars as pl
import gardenpipe.data as gd
from gardenpipe.data import FeatureLoader, LoadHint, MultiSourceLoader

BASE = dt.datetime(2026, 1, 5)
ROWS = 6_000
LABELS = ["A", "B", "C"]
rng = np.random.default_rng(7)
level = rng.normal(size=ROWS).cumsum()
t0 = int(BASE.replace(tzinfo=dt.timezone.utc).timestamp()) * 10**9
ns = t0 + np.arange(ROWS) * 1_000_000_000


def col(kind):
    s = pl.Series("time", ns, dtype=pl.Int64)
    d = s.cast(pl.Datetime("ns"))
    if kind.startswith("dt_"):
        parts = kind.split("_")
        out = d.cast(pl.Datetime(parts[1]))
        if len(parts) > 2:
            tz = {"utc": "UTC", "ams": "Europe/Amsterdam"}[parts[2]]
            out = out.dt.replace_time_zone("UTC").dt.convert_time_zone(tz)
        return out
    if kind == "int64_ns": return s
    if kind == "date": return d.dt.date().alias("time")
    if kind == "time_of_day": return d.dt.time().alias("time")
    if kind == "duration_ns": return (d - d.min()).alias("time")
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


KINDS = ["dt_ns", "dt_us", "dt_ms", "dt_ns_utc", "dt_us_ams", "int64_ns", "uint64_ns", "int64_small", "int32_small",
         "uint32_small", "float64_ns", "float64_small", "string_iso", "string_space", "date", "time_of_day", "duration_ns"]
date = "20260105"
root = Path(tempfile.mkdtemp(dir=sys.argv[1]))
out = {}
for kind in KINDS:
    df = pl.DataFrame({"time": col(kind), "level": level, "station": [LABELS[i % 3] for i in range(ROWS)]})
    path = root / kind
    path.mkdir()
    df.write_parquet(path / f"panel_{date}.parquet", row_group_size=500)
    for label in LABELS:
        df.filter(pl.col("station") == label).drop("station").write_parquet(path / f"{label}_{date}.parquet", row_group_size=200)
    for horizon in ("5s", "5m"):
        for files in ("shared", "each"):
            for layout in ("wide", "long"):
                for engine in ("streaming", "in-memory"):
                    args = dict(feature_exprs={"level": pl.col("level")}, targets={"y": pl.col("level")}, horizons=horizon)
                    template = "panel_{date}.parquet" if files == "shared" else "{source}_{date}.parquet"
                    base = FeatureLoader(path=f"{path}/{template}", **args)
                    loader = MultiSourceLoader(LABELS, base, label_col="station" if files == "shared" else None, layout=layout)
                    key = f"{kind}|{horizon}|{files}|{layout}|{engine}"
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
