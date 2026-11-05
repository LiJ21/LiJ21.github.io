"""Compare error structure across models: python model_diagnostics.py OUT_DIR"""

import sys, json, itertools
import numpy as np, polars as pl

sys.path.insert(0, "examples/weather")
import common as C

root = "."
base = pl.read_parquet("runs/weather/predictions.parquet").sort("issue_time")
obs, now = base["T_observed"].to_numpy(), base["T_now"].to_numpy()
hist = base["pred_history"].to_numpy()
xgb = np.load(sys.argv[1] + "/pred_xgb_history.npy")
ri = np.load(sys.argv[1] + "/pred_ridge_interactions.npy")
# 1. Does the month x hour bias repeat between test years?
D = base.with_columns(
    h=pl.col("issue_time").dt.hour(),
    mo=pl.col("issue_time").dt.month(),
    y=pl.col("issue_time").dt.year(),
    e=pl.Series(hist - obs),
    ex=pl.Series(xgb - obs),
    ei=pl.Series(ri - obs),
)
for col in ("e", "ei", "ex"):
    m = D.group_by("y", "mo", "h").agg(pl.col(col).mean().alias("b"), pl.len().alias("n"))
    a = m.filter(pl.col("y") == 2015).select("mo", "h", "b", "n")
    b = m.filter(pl.col("y") == 2016).select(
        "mo", "h", pl.col("b").alias("b2"), pl.col("n").alias("n2")
    )
    j = a.join(b, on=["mo", "h"])
    r = np.corrcoef(j["b"], j["b2"])[0, 1]
    w = (j["n"] + j["n2"]).to_numpy()
    cross = float((j["b"] * j["b2"] * (j["n"] + j["n2"])).sum() / (D[col] ** 2).sum())
    print(
        f'{col}: month x hour bias 2015 vs 2016 corr {r:.3f}; repeatable share of MSE (cross-year product) {cross:.3f}; total-share within-sample {float(D.group_by("mo","h").agg((pl.col(col).mean()**2*pl.len()).alias("s"))["s"].sum()/(D[col]**2).sum()):.3f}'
    )
# 2. xgb diagnostics on the same terms.
for nm, f in (("ridge", hist), ("ridge+int", ri), ("xgb", xgb)):
    e = f - obs
    dp = f - now
    chg = obs - now
    s, i = np.polyfit(dp, chg, 1)
    ser = pl.DataFrame({"t": base["issue_time"], "e": e})
    ac = []
    for lag in (1, 3, 6, 24):
        j = ser.join(ser.with_columns(pl.col("t") + pl.duration(hours=lag)), on="t", suffix="_l")
        ac.append(round(float(np.corrcoef(j["e"], j["e_l"])[0, 1]), 3))
    a = np.abs(e)
    print(
        nm,
        "MAE %.3f RMSE %.3f r2chg %.3f slope %.3f skill %.3f p95 %.2f within2 %.3f acf1/3/6/24 %s"
        % (
            a.mean(),
            np.sqrt((e**2).mean()),
            1 - (e**2).sum() / ((chg - chg.mean()) ** 2).sum(),
            s,
            1 - a.mean() / np.abs(now - obs).mean(),
            np.quantile(a, 0.95),
            (a <= 2).mean(),
            ac,
        ),
    )
# Weekly block bootstrap of the MAE gap.
wk = base.with_columns(
    w=(
        pl.col("issue_time").dt.year().cast(pl.Int32) * 100
        + pl.col("issue_time").dt.week().cast(pl.Int32)
    )
)["w"].to_numpy()
ids, inv = np.unique(wk, return_inverse=True)
n = len(ids)
cnt = np.bincount(inv, minlength=n)
sa = np.bincount(inv, np.abs(hist - obs), n)
sb = np.bincount(inv, np.abs(xgb - obs), n)
rng = np.random.default_rng(0)
g = []
for _ in range(4000):
    w = np.bincount(rng.integers(0, n, n), minlength=n)
    g.append(1 - (w * sb).sum() / (w * sa).sum())
print(
    "xgb MAE reduction vs ridge: %.3f 95%% %.3f..%.3f"
    % (1 - np.abs(xgb - obs).mean() / np.abs(hist - obs).mean(), *np.quantile(g, [0.025, 0.975]))
)
print(
    "xgb worse than ridge in n of 24 hours / 12 months:",
    sum(
        D.filter(pl.col("h") == h)["ex"].abs().mean() > D.filter(pl.col("h") == h)["e"].abs().mean()
        for h in range(24)
    ),
    sum(
        D.filter(pl.col("mo") == m)["ex"].abs().mean()
        > D.filter(pl.col("mo") == m)["e"].abs().mean()
        for m in range(1, 13)
    ),
)
