"""MultiSourceLoader with a different time unit on each stream: a digest of every batch, to compare two checkouts.

    PYTHONPATH=CHECKOUT python multi_source_units.py SCRATCH_DIR > CODE.json
    python3 multi_source_units.py --compare BEFORE.json AFTER.json

Window ends come from the union of the streams, so an end from the nanosecond stream can fall between the
ticks of a coarser one, and a bound in that stream's unit has to be rounded. This covers that case, on times
after and before 1970, where rounding down and rounding towards zero differ.
"""
import hashlib, json, sys, tempfile, datetime as dt

if sys.argv[1] == "--compare":
    a, b = (json.load(open(path)) for path in sys.argv[2:4])
    print(f"polars {a['polars']}: {a['data']} against {b['data']}")
    for key, x in a["out"].items():
        print("same" if x == b["out"][key] else "DIFF", key, x)
    print(sum(x == b["out"][key] for key, x in a["out"].items()), "of", len(a["out"]), "identical")
    raise SystemExit

from pathlib import Path
import numpy as np, polars as pl
import gardenpipe.data as gd
from gardenpipe.data import FeatureLoader, LoadHint, MultiSourceLoader

ROWS = 4_000
date = "20260105"
units = {"A": "ns", "B": "us", "C": "ms"}
rng = np.random.default_rng(13)
root = Path(tempfile.mkdtemp(dir=sys.argv[1]))
out = {}
for era, start in (("after 1970", dt.datetime(2026, 1, 5)), ("before 1970", dt.datetime(1960, 1, 5))):
    t0 = int((start.replace(tzinfo=dt.timezone.utc) - dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)).total_seconds()) * 10**9
    path = root / era.replace(" ", "_")
    path.mkdir()
    for label, unit in units.items():
        ns = t0 + np.sort(rng.integers(0, 3_600 * 10**9, ROWS))
        frame = pl.DataFrame({"time": pl.Series(ns, dtype=pl.Int64).cast(pl.Datetime("ns")).cast(pl.Datetime(unit)).sort(), "level": rng.normal(size=ROWS).cumsum()})
        frame.write_parquet(path / f"{label}_{date}.parquet", row_group_size=200)
    for horizon in ("5s", "1500us"):
        for batch in (700, 3000):
            for layout in ("wide", "long"):
                for engine in ("streaming", "in-memory"):
                    base = FeatureLoader(path=f"{path}/{{source}}_{{date}}.parquet", feature_exprs={"level": pl.col("level")}, targets={"y": pl.col("level")}, horizons=horizon)
                    loader = MultiSourceLoader(list(units), base, layout=layout)
                    key = f"{era}|{horizon}|batch {batch}|{layout}|{engine}"
                    try:
                        h = hashlib.sha256(); rows = 0; batches = 0
                        for frame in loader.iter_date_frames([date], hint=LoadHint(batch_size=batch, polars_engine=engine)):
                            b = frame.lf.collect()
                            rows += b.height; batches += 1
                            h.update(b.select(pl.all().cast(pl.String, strict=False)).write_csv().encode())
                        out[key] = f"{rows} rows {batches} batches {h.hexdigest()[:12]}"
                    except Exception as e:
                        out[key] = f"ERROR {type(e).__name__}: {str(e).splitlines()[0][:70]}"
print(json.dumps(dict(polars=pl.__version__, data=hashlib.sha256(Path(gd.__file__).read_bytes()).hexdigest()[:12], out=out)))
