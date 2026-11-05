"""Selection on validation folds only, then one test score. Run from a GardenPipe checkout: python compare_models.py OUT_DIR"""

import json, sys, time
from pathlib import Path
import numpy as np, polars as pl

sys.path.insert(0, "examples/weather")
import common as C
from gardenpipe.data import FeatureLoader
from gardenpipe.model import RidgeAdapter, XGBoostAdapter
from gardenpipe.pipeline import Pipeline
from gardenpipe.score import rmse
from gardenpipe.search import grid
from gardenpipe.transform import Standardizer

base = pl.read_parquet("runs/weather/predictions.parquet").sort("issue_time")
obs, now = base["T_observed"].to_numpy(), base["T_now"].to_numpy()
# Season-by-hour terms and a second daily harmonic: what a linear model needs if the cycle changes shape.
tau = 2 * np.pi
day = (
    pl.col("time").dt.hour().cast(pl.Int32) * 60 + pl.col("time").dt.minute().cast(pl.Int32)
) / 1440
year = (pl.col("time").dt.ordinal_day() - 1) / 365.25
extra = {
    "td_ss": (day * tau).sin() * (year * tau).sin(),
    "td_sc": (day * tau).sin() * (year * tau).cos(),
    "td_cs": (day * tau).cos() * (year * tau).sin(),
    "td_cc": (day * tau).cos() * (year * tau).cos(),
    "tod2_sin": (day * 2 * tau).sin(),
    "tod2_cos": (day * 2 * tau).cos(),
}


def loader(ex=False):
    fe = C.feature_exprs()
    if ex:
        fe = {**fe, **extra}
    return FeatureLoader(
        path=f"{C.DATA_DIR}/jena_{{date}}.parquet",
        feature_exprs=fe,
        stateful_features=C.stateful_features(),
        targets={C.TARGET: pl.col("T")},
        horizons=C.HORIZON,
        target_tolerance="0s",
    )


rule = (C.eligible(),)


def run(name, adapter, feats, space, ex=False, transform=True):
    kw = dict(transform=Standardizer(feats)) if transform else {}
    t = time.perf_counter()
    n = int(np.prod([len(v) for v in space.values()])) if space else 1
    pipe = Pipeline(
        rolling_dates=C.ROLLING_DATES,
        test_dates=C.TEST_DATES,
        adapter=adapter,
        target=C.TARGET,
        features=feats,
        data_loader=loader(ex),
        train_sampler=rule,
        val_sampler=rule,
        test_sampler=rule,
        search_space={k: grid(v) for k, v in space.items()},
        search_sampler="grid",
        n_trials=n,
        val_score=rmse,
        score_direction="minimize",
        seed=0,
        polars_engine="in-memory",
        **kw,
    )
    res = pipe.train()
    fr = pipe.predict_frame(C.TEST_DATES, key_cols=["time"], time_col="time").sort("time")
    assert fr["time"].equals(base["issue_time"])
    p = now + fr["prediction"].to_numpy()
    e = p - obs
    out = dict(
        model=name,
        val_rmse=float(res["best_score"]),
        params=res["best_params"],
        test_mae=float(np.abs(e).mean()),
        test_rmse=float(np.sqrt((e**2).mean())),
        bias=float(e.mean()),
        seconds=time.perf_counter() - t,
    )
    if hasattr(pipe.model, "num_boosted_rounds"):
        out["rounds"] = pipe.model.num_boosted_rounds()
        out["cv_rounds"] = [r["best_num_boost_round"] for r in adapter.fit_history if r["role"] == "cv"]
    print(json.dumps(out))
    (Path(sys.argv[1]) / f"{name}.json").write_text(json.dumps(out))
    np.save(f"{sys.argv[1]}/pred_{name}.npy", p)
    return pipe


H = C.RECIPES["history"]
X = H + list(extra)
run(
    "ridge_interactions",
    RidgeAdapter(batch_size=20000),
    X,
    {"alpha": [0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]},
    ex=True,
)
for name, F, ex in (("xgb_history", H, False), ("xgb_interactions", X, True)):
    run(
        name,
        # The round count is an adapter setting, not a parameter: in a search space it is ignored.
        # Early stopping on the validation folds picks it, and the refit uses their median.
        XGBoostAdapter(batch_size=20000, num_boost_round=5000, early_stopping_rounds=50),
        F,
        {
            "max_depth": [3, 5, 7, 9, 11],
            "eta": [0.02, 0.05],
            "subsample": [0.8],
            "colsample_bytree": [0.8],
        },
        ex=ex,
        transform=False,
    )
