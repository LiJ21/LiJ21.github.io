"""Instruments in one file and sources in several: every batch, published against patched.

    PYTHONPATH=CHECKOUT python multi_source_check.py SCRATCH_DIR > CODE.json
    python3 multi_source_check.py --compare PUBLISHED.json PATCHED.json

Three instruments on irregular, partly shared timestamps. For each loader it prints a digest of every
batch, how many batches end at or after the start of the next, and a digest of the window ends.
"""
import hashlib, json, sys, tempfile, datetime as dt

if sys.argv[1] == "--compare":
    a, b = (json.load(open(path)) for path in sys.argv[2:4])
    print(f"polars {a['polars']}: published {a['data']}, patched {b['data']}")
    for case, x in a["out"].items():
        y = b["out"][case]
        print("same" if x == y else "DIFF", case, f"{x['rows']} rows, {x['batches']} batches, timestamps in two batches {x['timestamps_in_two_batches']} and {y['timestamps_in_two_batches']}")
    print(sum(x == b["out"][case] for case, x in a["out"].items()), "of", len(a["out"]), "identical")
    raise SystemExit

from pathlib import Path
import numpy as np, polars as pl
import gardenpipe.data as gd
from gardenpipe.data import FeatureLoader, LoadHint, MultiSourceLoader
from gardenpipe.features import EwmaFeature

root = Path(tempfile.mkdtemp(dir=sys.argv[1]))
date = "2026-01-05"
rng = np.random.default_rng(11)
t0 = dt.datetime(2026, 1, 5)
frames = []
shared = np.sort(rng.choice(40_000, 6_000, replace=False))     # ticks every instrument trades
for i, name in enumerate(("A", "B", "C")):
    own = np.sort(rng.choice(40_000, 3_000 + 2_000 * i, replace=False))
    ticks = np.unique(np.concatenate([shared, own]))
    t = pl.Series([t0 + dt.timedelta(milliseconds=int(x) * 50) for x in ticks], dtype=pl.Datetime("ns"))
    frames.append(pl.DataFrame({"time": t, "symbol": name, "px": 100 + rng.normal(size=len(ticks)).cumsum() / 10}))
one_file = pl.concat(frames).sort("time", "symbol", maintain_order=True)
one_file.write_parquet(root / f"all_{date}.parquet", row_group_size=2_000)
for f in frames:
    f.write_parquet(root / f"{f['symbol'][0]}_{date}.parquet", row_group_size=2_000)

args = dict(feature_exprs={"px": pl.col("px")}, stateful_features=(EwmaFeature("ewm", pl.col("px"), half_life="5s"),),
            targets={"y": pl.col("px")}, horizons="5s")
loaders = {
    "instruments in one file, target_by": FeatureLoader(path=f"{root}/all_{{date}}.parquet", target_by=("symbol",), **args),
    "MultiSourceLoader, one shared file, wide": MultiSourceLoader(["A", "B", "C"], FeatureLoader(path=f"{root}/all_{{date}}.parquet", **args), label_col="symbol", layout="wide"),
    "MultiSourceLoader, one shared file, long": MultiSourceLoader(["A", "B", "C"], FeatureLoader(path=f"{root}/all_{{date}}.parquet", **args), label_col="symbol", layout="long"),
    "MultiSourceLoader, one file per source, wide": MultiSourceLoader(["A", "B", "C"], FeatureLoader(path=f"{root}/{{source}}_{{date}}.parquet", **args), layout="wide"),
    "MultiSourceLoader, one file per source, long": MultiSourceLoader(["A", "B", "C"], FeatureLoader(path=f"{root}/{{source}}_{{date}}.parquet", **args), layout="long"),
}
out = {}
for name, loader in loaders.items():
    for batch_size in (700, 3_000):
        for engine in ("streaming", "in-memory"):
            key = f"{name} | batch {batch_size} | {engine}"
            digest = hashlib.sha256()
            rows, ends, split = 0, [], 0
            last_end = None
            for frame in loader.iter_date_frames([date], hint=LoadHint(batch_size=batch_size, polars_engine=engine)):
                b = frame.lf.collect()
                rows += b.height
                first, end = b["time"].min(), b["time"].max()
                split += int(last_end is not None and first <= last_end)
                last_end = end
                ends.append(str(end))
                digest.update(b.sort(b.columns).write_csv().encode())
            out[key] = dict(rows=rows, batches=len(ends), digest=digest.hexdigest()[:12], timestamps_in_two_batches=split,
                            ends=hashlib.sha256("|".join(ends).encode()).hexdigest()[:12])
print(json.dumps(dict(polars=pl.__version__, data=hashlib.sha256(Path(gd.__file__).read_bytes()).hexdigest()[:12], out=out)))
