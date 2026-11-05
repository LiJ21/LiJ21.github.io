"""Gradient boosting through the same loader and folds, to measure what the model itself holds."""

import argparse, json
from pathlib import Path
import numpy as np, polars as pl
from gardenpipe.data import FeatureLoader, expand_dates
from gardenpipe.features import EwmaFeature
from gardenpipe.model import XGBoostAdapter
from gardenpipe.pipeline import Pipeline
from gardenpipe.score import r2
from gardenpipe.search import grid

from run_record import Stopwatch

ap = argparse.ArgumentParser()
ap.add_argument("--data", type=Path, required=True)
ap.add_argument("--days", type=int, required=True)
ap.add_argument("--external", action="store_true")
ap.add_argument("--tag", default="xgb")
ap.add_argument("--cache", default="/tmp/x")
ap.add_argument("--out", type=Path)
a = ap.parse_args()
dates = expand_dates("20260105-20271231")[: a.days]
k = max(1, len(dates) // 5)
loader = FeatureLoader(
    path=f"{a.data}/sensor_{{date}}.parquet",
    feature_exprs={"level": pl.col("level")},
    stateful_features=(EwmaFeature("level_ewm_1m", pl.col("level"), half_life="1m"),),
    targets={"change_5m": pl.col("level")},
    horizons="5m",
)
keep = pl.col("change_5m").is_not_null()
pipe = Pipeline(
    rolling_dates=[dates[: 2 * k], dates[2 * k : 3 * k], dates[3 * k : 4 * k]],
    test_dates=dates[4 * k :],
    adapter=XGBoostAdapter(
        batch_size=100_000, num_boost_round=10, external_memory=a.external, cache_dir=a.cache
    ),
    target="change_5m",
    features=["level", "level_ewm_1m"],
    data_loader=loader,
    train_sampler=(keep,),
    val_sampler=(keep,),
    test_sampler=(keep,),
    val_score=r2,
    score_direction="maximize",
    search_space={"max_depth": grid([4])},
    search_sampler="grid",
    n_trials=1,
)
clock = Stopwatch()
pipe.train()
res = pipe.test(score=r2, keep_predictions=False)
measured = clock.record()
o = dict(
    tag=a.tag,
    mode="external" if a.external else "in-core",
    days=a.days,
    total_rows=4_000_000 * a.days,
    **measured,
    test_r2=float(res["test_score"]),
)
print(json.dumps(o))
if a.out:
    open(a.out, "a").write(json.dumps(o) + "\n")
