"""One measured GardenPipe run, in a fresh process. Mirrors examples/minimal.py with the knobs exposed.

The data must already exist: generate_data.py writes it in a separate process.
"""

import argparse, json
from pathlib import Path
import numpy as np, polars as pl
from gardenpipe.buffered import BufferConfig, buffered_wrapper, required_buffer_bytes
from gardenpipe.data import FeatureLoader, expand_dates
from gardenpipe.features import EwmaFeature
from gardenpipe.model import RidgeAdapter
from gardenpipe.pipeline import Pipeline
from gardenpipe.score import r2

from run_record import Stopwatch

ap = argparse.ArgumentParser()
ap.add_argument("--data", type=Path, required=True)
ap.add_argument("--rows", type=int, required=True)
ap.add_argument("--days", type=int, required=True)
ap.add_argument("--batch", type=int, default=100_000)
ap.add_argument("--buffer-mib", type=float, default=64)
ap.add_argument("--workers", type=int, default=2)
ap.add_argument("--mode", choices=["stream", "materialize"], default="stream")
ap.add_argument("--tag", default="")
ap.add_argument("--page-cache", default="unknown", help="cold or warm, as set by page_cache.py")
ap.add_argument("--out", type=Path)
a = ap.parse_args()


dates = expand_dates("20260105-20271231")[: a.days]
assert len(dates) == a.days, len(dates)
k = max(1, len(dates) // 5)
missing = [d for d in dates if not (a.data / f"sensor_{d}.parquet").exists()]
if missing:
    raise SystemExit(f"{len(missing)} files missing from {a.data}; run generate_data.py first")
loader = FeatureLoader(
    path=f"{a.data}/sensor_{{date}}.parquet",
    feature_exprs={"level": pl.col("level")},
    stateful_features=(EwmaFeature("level_ewm_1m", pl.col("level"), half_life="1m"),),
    targets={"change_5m": pl.col("level")},
    horizons="5m",
)
keep = pl.col("change_5m").is_not_null()
kw = {}
if a.mode == "stream":
    kw["data_source_wrapper"] = buffered_wrapper(
        BufferConfig(workers=a.workers, max_buffer_bytes=int(a.buffer_mib * 2**20))
    )
pipe = Pipeline(
    rolling_dates=[dates[: 2 * k], dates[2 * k : 3 * k], dates[3 * k : 4 * k]],
    test_dates=dates[4 * k :],
    adapter=RidgeAdapter(batch_size=a.batch, streaming=a.mode == "stream"),
    target="change_5m",
    features=["level", "level_ewm_1m"],
    data_loader=loader,
    train_sampler=(keep,),
    val_sampler=(keep,),
    test_sampler=(keep,),
    val_score=r2,
    score_direction="maximize",
    n_trials=1,
    **kw,
)
clock = Stopwatch()
pipe.train()
res = pipe.test(score=r2, keep_predictions=False)
measured = clock.record()
disk = sum((a.data / f"sensor_{d}.parquet").stat().st_size for d in dates)
out = dict(
    tag=a.tag,
    mode=a.mode,
    rows=a.rows,
    days=a.days,
    total_rows=a.rows * a.days,
    batch=a.batch,
    buffer_mib=a.buffer_mib,
    workers=a.workers,
    page_cache=a.page_cache,
    disk_mib=disk / 2**20,
    **measured,
    test_r2=float(res["test_score"]),
    test_n=int(res["n"]),
    coef=[float(x) for x in pipe.model.coef],
    intercept=float(pipe.model.intercept),
)
line = json.dumps(out)
print(line)
if a.out:
    with a.out.open("a") as f:
        f.write(line + "\n")
