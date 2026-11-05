"""Ridge on random Fourier features through GardenPipe's real streaming path. Peak RSS is measured per process."""

import argparse, json, sys
from dataclasses import dataclass, field
import numpy as np, polars as pl

sys.path.insert(0, "examples/weather")
import common as C
from gardenpipe.data import as_batch
from gardenpipe.model import RidgeAdapter, _LinearStats
from gardenpipe.pipeline import Pipeline
from gardenpipe.score import rmse
from gardenpipe.search import grid
from gardenpipe.transform import Standardizer

from run_record import Stopwatch

ap = argparse.ArgumentParser()
ap.add_argument("--D", type=int, default=2000)
ap.add_argument("--gamma", type=float, default=0.05)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--chunk", type=int, default=2000)
ap.add_argument("--out")
ap.add_argument("--pred-dir", default=".")
a = ap.parse_args()
d0 = len(C.RECIPES["history"])
rng = np.random.default_rng(a.seed)
W = rng.normal(scale=np.sqrt(2 * a.gamma), size=(d0, a.D))
B = rng.uniform(0, 2 * np.pi, a.D)
S = np.sqrt(2 / a.D) if a.D else 0.0


def phi(x):
    return np.hstack([x, S * np.cos(x @ W + B)]) if a.D else x


@dataclass
class RFFRidge(RidgeAdapter):
    def _stats(self, src):
        key = self._stats_key(src)
        if key is not None and key in self._stats_cache:
            return self._stats_cache[key]
        stats = None
        for value in src.batches(self.batch_size):
            b = as_batch(value)
            x = np.asarray(b.x, dtype=np.float64)
            y = np.asarray(b.y).reshape(-1)
            for i in range(0, len(y), a.chunk):  # the map costs chunk x d x 8 bytes while it lives
                f = phi(x[i : i + a.chunk])
                yy = y[i : i + a.chunk]
                if stats is None:
                    stats = _LinearStats.empty(f.shape[1], np, np.float64)
                stats.add(f, yy, None)
        if key is not None:
            self._stats_cache[key] = stats
        return stats

    def predict(self, model, x):
        x = np.asarray(x, dtype=np.float64)
        return (
            np.concatenate(
                [model.predict(phi(x[i : i + a.chunk])) for i in range(0, len(x), a.chunk)]
            )
            if len(x)
            else np.empty(0)
        )


feats = C.RECIPES["history"]
rule = (C.eligible(),)
alphas = [0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]
clock = Stopwatch()
pipe = Pipeline(
    rolling_dates=C.ROLLING_DATES,
    test_dates=C.TEST_DATES,
    adapter=RFFRidge(batch_size=20000),
    target=C.TARGET,
    features=feats,
    data_loader=C.make_loader(),
    transform=Standardizer(feats),
    train_sampler=rule,
    val_sampler=rule,
    test_sampler=rule,
    search_space={"alpha": grid(alphas)},
    search_sampler="grid",
    n_trials=len(alphas),
    val_score=rmse,
    score_direction="minimize",
    seed=0,
    polars_engine="in-memory",
)
res = pipe.train()
fr = pipe.predict_frame(C.TEST_DATES, key_cols=["time"], time_col="time").sort("time")
base = pl.read_parquet("runs/weather/predictions.parquet").sort("issue_time")
assert fr["time"].equals(base["issue_time"])
now, obs = base["T_now"].to_numpy(), base["T_observed"].to_numpy()
p = now + fr["prediction"].to_numpy()
e = p - obs
out = dict(
    D=a.D,
    gamma=a.gamma,
    seed=a.seed,
    d=d0 + a.D,
    val_rmse=float(res["best_score"]),
    alpha=res["best_params"]["alpha"],
    mae=float(np.abs(e).mean()),
    rmse=float(np.sqrt((e**2).mean())),
    bias=float(e.mean()),
    **clock.record(),
    gram_mib=(d0 + a.D) ** 2 * 8 / 2**20,
    trials=[
        (tt.params["alpha"], round(tt.value, 4))
        for tt in sorted(pipe.study.trials, key=lambda t: t.params["alpha"])
    ],
)
print(json.dumps(out))
np.save(f"{a.pred_dir}/pipe_rff_{a.D}_{a.gamma}_{a.seed}.npy", p)
if a.out:
    open(a.out, "a").write(json.dumps(out) + "\n")
