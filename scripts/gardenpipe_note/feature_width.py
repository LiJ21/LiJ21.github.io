"""How far does a fixed-memory linear model get as its width grows? NumPy only, same rows and folds.

Run from a GardenPipe checkout after examples/weather/train.py: python feature_width.py
"""

import numpy as np
import polars as pl

from weather_frame import HISTORY, load_weather

ALPHAS = [1e-1, 1, 10, 100, 1e3, 1e4, 1e5, 1e6]
frame = load_weather()
years = frame["year"].to_numpy()
x0 = frame.select(HISTORY).to_numpy()
y = frame["change_6h"].to_numpy()
test = frame.filter(pl.col("year") >= 2015)
now = test["T"].to_numpy()
observed = now + test["change_6h"].to_numpy()
FOLDS = [(years <= 2012, years == 2013), (years <= 2013, years == 2014)]
FINAL, TEST = years <= 2014, years >= 2015


def path_rmse(f, train, valid):
    mean, y_mean = f[train].mean(0), y[train].mean()
    centered = f[train] - mean
    values, vectors = np.linalg.eigh(centered.T @ centered)
    projected = vectors.T @ (centered.T @ (y[train] - y_mean))
    out = {}
    for alpha in ALPHAS:
        coef = vectors @ (projected / (values + alpha))
        out[alpha] = float(np.mean(((f[valid] - mean) @ coef + y_mean - y[valid]) ** 2))
    return out


def evaluate(name, feature_map):
    totals = dict.fromkeys(ALPHAS, 0.0)
    for train, valid in FOLDS:
        mean, scale = x0[train].mean(0), x0[train].std(0)
        scores = path_rmse(feature_map((x0 - mean) / scale), train, valid)
        for alpha in ALPHAS:
            totals[alpha] += scores[alpha] * valid.sum()
    count = sum(valid.sum() for _, valid in FOLDS)
    best = min(totals, key=totals.get)
    mean, scale = x0[FINAL].mean(0), x0[FINAL].std(0)
    f = feature_map((x0 - mean) / scale)
    f_mean, y_mean = f[FINAL].mean(0), y[FINAL].mean()
    centered = f[FINAL] - f_mean
    coef = np.linalg.solve(centered.T @ centered + best * np.eye(f.shape[1]), centered.T @ (y[FINAL] - y_mean))
    error = now + (f[TEST] - f_mean) @ coef + y_mean - observed
    print(
        f"{name}: d={f.shape[1]} alpha={best:g} validation RMSE {np.sqrt(totals[best] / count):.3f}"
        f" test MAE {np.abs(error).mean():.3f} test RMSE {np.sqrt((error ** 2).mean()):.3f}",
        flush=True,
    )


def pairwise(z):
    i, j = np.triu_indices(z.shape[1])
    return np.hstack([z, z[:, i] * z[:, j]])


def fourier(count, gamma):
    rng = np.random.default_rng(0)
    w = rng.normal(scale=np.sqrt(2 * gamma), size=(x0.shape[1], count))
    b = rng.uniform(0, 2 * np.pi, count)
    return lambda z: np.hstack([z, np.sqrt(2 / count) * np.cos(z @ w + b)])


evaluate("linear", lambda z: z)
evaluate("pairwise products", pairwise)
for count, gamma in ((500, 0.05), (2000, 0.05), (2000, 0.1), (4000, 0.05), (4000, 0.1)):
    evaluate(f"random features D={count} gamma={gamma}", fourier(count, gamma))
