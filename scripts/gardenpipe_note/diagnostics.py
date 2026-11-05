"""Fit diagnostics for the Ridge forecasts: python diagnostics.py runs/weather/predictions.parquet OUT_DIR"""

import json, sys
import numpy as np, polars as pl

p = pl.read_parquet(sys.argv[1]).sort("issue_time")
obs, now = p["T_observed"].to_numpy(), p["T_now"].to_numpy()
chg = obs - now
M = {k: p[f"pred_{k}"].to_numpy() for k in ("persistence", "seasonal", "calendar", "history")}


def line(k):
    f = M[k]
    e = f - obs
    dp = f - now
    r = dict(
        mae=np.abs(e).mean(),
        rmse=np.sqrt((e**2).mean()),
        bias=e.mean(),
        r2_level=1 - (e**2).sum() / ((obs - obs.mean()) ** 2).sum(),
        r2_change=1 - (e**2).sum() / ((chg - chg.mean()) ** 2).sum(),
    )
    if dp.std() > 0:
        s, i = np.polyfit(dp, chg, 1)
        r.update(corr_change=np.corrcoef(dp, chg)[0, 1], cal_slope=s, cal_intercept=i)
    return r


for k in M:
    print(k, {a: round(float(b), 4) for a, b in line(k).items()})
print("target: mean change %.3f, sd %.3f; sd of level %.2f" % (chg.mean(), chg.std(), obs.std()))
e = M["history"] - obs
a = np.abs(e)
print(
    "history abs err: median %.2f p90 %.2f p95 %.2f p99 %.2f max %.2f"
    % tuple(np.quantile(a, [0.5, 0.9, 0.95, 0.99, 1]))
)
print(
    "within 1/2/3/5 C: ",
    [round(float((a <= t).mean()), 3) for t in (1, 2, 3, 5)],
    " persistence:",
    [round(float((np.abs(M["persistence"] - obs) <= t).mean()), 3) for t in (1, 2, 3, 5)],
)
z = (e - e.mean()) / e.std()
print("skew %.3f excess kurt %.3f" % ((z**3).mean(), (z**4).mean() - 3))
print("error quantiles 5/25/50/75/95", np.round(np.quantile(e, [0.05, 0.25, 0.5, 0.75, 0.95]), 2))
t = p["issue_time"].to_numpy()
ser = pl.DataFrame({"t": p["issue_time"], "e": e})
for lag in (1, 3, 6, 12, 24, 48, 168):
    j = ser.join(ser.with_columns(pl.col("t") + pl.duration(hours=lag)), on="t", suffix="_l")
    print(f'error autocorr lag {lag}h: {np.corrcoef(j["e"],j["e_l"])[0,1]:.3f} (n={j.height})')
# Nonoverlap 6-hourly effective n: block bootstrap by week.
wk = p.with_columns(
    w=(
        pl.col("issue_time").dt.year().cast(pl.Int32) * 100
        + pl.col("issue_time").dt.week().cast(pl.Int32)
    )
)["w"].to_numpy()
ids, inv = np.unique(wk, return_inverse=True)
rng = np.random.default_rng(0)
B = 4000
n = len(ids)


def agg(x):
    return np.bincount(inv, x, n), np.bincount(inv, minlength=n)


cnt = np.bincount(inv, minlength=n)
sums = {
    k: (np.bincount(inv, np.abs(M[k] - obs), n), np.bincount(inv, (M[k] - obs) ** 2, n)) for k in M
}
res = {
    k: [] for k in ("mae_hist", "rmse_hist", "skill", "skill_rmse", "hist_minus_cal", "seas_skill")
}
for _ in range(B):
    w = np.bincount(rng.integers(0, n, n), minlength=n)
    c = (w * cnt).sum()
    mae = {k: (w * sums[k][0]).sum() / c for k in M}
    rm = {k: np.sqrt((w * sums[k][1]).sum() / c) for k in M}
    res["mae_hist"].append(mae["history"])
    res["rmse_hist"].append(rm["history"])
    res["skill"].append(1 - mae["history"] / mae["persistence"])
    res["skill_rmse"].append(1 - rm["history"] / rm["persistence"])
    res["hist_minus_cal"].append(mae["history"] - mae["calendar"])
    res["seas_skill"].append(1 - mae["seasonal"] / mae["persistence"])
for k, v in res.items():
    print(f"{k}: {np.quantile(v,.025):.3f} .. {np.quantile(v,.975):.3f}")
print("weeks", n)
D = p.with_columns(
    h=pl.col("issue_time").dt.hour(),
    mo=pl.col("issue_time").dt.month(),
    y=pl.col("issue_time").dt.year(),
    e=pl.Series(e),
    ae=pl.Series(a),
    ep=pl.Series(M["persistence"] - obs),
    ec=pl.Series(M["calendar"] - obs),
)
print(
    D.group_by("y")
    .agg(
        n=pl.len(),
        mae=pl.col("ae").mean(),
        rmse=(pl.col("e") ** 2).mean().sqrt(),
        bias=pl.col("e").mean(),
        maep=pl.col("ep").abs().mean(),
    )
    .sort("y")
)
print(
    D.group_by("mo")
    .agg(
        n=pl.len(), mae=pl.col("ae").mean(), bias=pl.col("e").mean(), maep=pl.col("ep").abs().mean()
    )
    .sort("mo")
    .with_columns(pl.col("mae", "bias", "maep").round(2))
)
print(
    D.group_by("h")
    .agg(mae=pl.col("ae").mean(), bias=pl.col("e").mean(), maep=pl.col("ep").abs().mean())
    .sort("h")
    .with_columns(pl.col("mae", "bias", "maep").round(2))
)
H = D.with_columns(
    season=pl.when(pl.col("mo").is_in([12, 1, 2]))
    .then(pl.lit("DJF"))
    .when(pl.col("mo").is_in([3, 4, 5]))
    .then(pl.lit("MAM"))
    .when(pl.col("mo").is_in([6, 7, 8]))
    .then(pl.lit("JJA"))
    .otherwise(pl.lit("SON"))
)
hm = D.group_by("mo", "h").agg(b=pl.col("e").mean(), n=pl.len())
print(
    "cell bias range: %.2f .. %.2f; sd of cell means %.2f; share of MSE from month x hour bias: %.3f"
    % (
        hm["b"].min(),
        hm["b"].max(),
        hm["b"].std(),
        float(((hm["b"] ** 2 * hm["n"]).sum()) / (e**2).sum()),
    )
)
print(hm.sort("b").head(4))
print(hm.sort("b", descending=True).head(4))
hm.write_csv(sys.argv[2] + "/heat_history.csv")
# Calibration by predicted decile.
q = D.with_columns(dp=pl.Series(M["history"] - now), chg=pl.Series(chg))
q = q.with_columns(bin=pl.col("dp").rank("ordinal").mul(20).floordiv(q.height + 1))
c = (
    q.group_by("bin")
    .agg(pred=pl.col("dp").mean(), act=pl.col("chg").mean(), n=pl.len(), sd=pl.col("chg").std())
    .sort("bin")
)
print(c.with_columns(pl.col("pred", "act", "sd").round(2)))
c.write_csv(sys.argv[2] + "/calib.csv")
print("worst")
print(
    D.with_columns(dp=pl.Series(M["history"] - now), chg=pl.Series(chg))
    .sort("ae", descending=True)
    .head(12)
    .select("issue_time", "T_now", "T_observed", "pred_history", "dp", "chg")
    .with_columns(pl.col("T_now", "T_observed", "pred_history", "dp", "chg").round(1))
)
big = (
    D.with_columns(day=pl.col("issue_time").dt.date())
    .group_by("day")
    .agg(pl.col("ae").mean().alias("m"))
    .sort("m", descending=True)
)
print("worst days", big.head(6).with_columns(pl.col("m").round(2)).rows())
top = np.sort(a)[::-1]
print(
    "share of total squared error from worst 1%%/5%% hours: %.3f %.3f"
    % (
        (np.sort(e**2)[::-1][: len(e) // 100]).sum() / (e**2).sum(),
        (np.sort(e**2)[::-1][: len(e) // 20]).sum() / (e**2).sum(),
    )
)
