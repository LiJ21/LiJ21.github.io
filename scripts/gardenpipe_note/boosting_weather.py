"""Gradient boosting on the weather data, with its peak memory. Run from a GardenPipe checkout."""

import json, sys
from pathlib import Path
import numpy as np, polars as pl

sys.path.insert(0, "examples/weather")
import common as C
from gardenpipe.model import XGBoostAdapter
from gardenpipe.pipeline import Pipeline
from gardenpipe.score import rmse
from gardenpipe.search import grid

from run_record import Stopwatch

choice = json.loads(Path(sys.argv[1], "xgb_history.json").read_text())
rule = (C.eligible(),)
H = C.RECIPES["history"]
clock = Stopwatch()
pipe = Pipeline(
    rolling_dates=C.ROLLING_DATES,
    test_dates=C.TEST_DATES,
    adapter=XGBoostAdapter(batch_size=20000, num_boost_round=choice["rounds"]),
    target=C.TARGET,
    features=H,
    data_loader=C.make_loader(),
    train_sampler=rule,
    val_sampler=rule,
    test_sampler=rule,
    search_space={name: grid([value]) for name, value in choice["params"].items()},
    search_sampler="grid",
    n_trials=1,
    val_score=rmse,
    score_direction="minimize",
    seed=0,
    polars_engine="in-memory",
)
pipe.train()
fr = pipe.predict_frame(C.TEST_DATES, key_cols=["time"], time_col="time").sort("time")
base = pl.read_parquet("runs/weather/predictions.parquet").sort("issue_time")
e = base["T_now"].to_numpy() + fr["prediction"].to_numpy() - base["T_observed"].to_numpy()
print(
    json.dumps(
        dict(
            **clock.record(),
            mae=float(np.abs(e).mean()),
            rmse=float(np.sqrt((e**2).mean())),
        )
    )
)
