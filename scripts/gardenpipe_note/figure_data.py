"""Export the two forecast weeks and the month-by-hour bias maps used by the figures.

Run from a GardenPipe checkout: python figure_data.py WORK_DIR
WORK_DIR needs pred_xgb_history.npy from compare_models.py and pipe_rff_2000_0.05_0.npy from
random_features.py. CSV files are written next to them, for collect.py.
"""

import sys

import numpy as np
import polars as pl

work = sys.argv[1]
base = pl.read_parquet("runs/weather/predictions.parquet").sort("issue_time")
observed = base["T_observed"].to_numpy()
errors = {
    "ridge": base["pred_history"].to_numpy() - observed,
    "xgb": np.load(f"{work}/pred_xgb_history.npy") - observed,
    "rff2000": np.load(f"{work}/pipe_rff_2000_0.05_0.npy") - observed,
}
for name, error in errors.items():
    frame = base.select(
        year=pl.col("issue_time").dt.year(),
        mo=pl.col("issue_time").dt.month(),
        h=pl.col("issue_time").dt.hour(),
        error=pl.Series(error),
    )
    frame.group_by("mo", "h").agg(b=pl.col("error").mean()).sort("mo", "h").write_csv(f"{work}/heat_{name}.csv")
    yearly = frame.group_by("year", "mo", "h").agg(b=pl.col("error").mean())
    pair = yearly.filter(pl.col("year") == 2015).join(
        yearly.filter(pl.col("year") == 2016), on=["mo", "h"], suffix="_next"
    )
    print(name, "bias map correlation, 2015 against 2016:", round(float(np.corrcoef(pair["b"], pair["b_next"])[0, 1]), 3))

average = (errors["xgb"] + errors["rff2000"]) / 2
print("average of boosting and 2,000 random features, test MAE:", round(float(np.abs(average).mean()), 4))

for name, start, stop in (("winter", "2015-01-12", "2015-01-19"), ("summer", "2015-07-13", "2015-07-20")):
    week = base.filter(pl.col("target_time").is_between(pl.lit(start).str.to_datetime("%Y-%m-%d"), pl.lit(stop).str.to_datetime("%Y-%m-%d")))
    week.select("target_time", "T_observed", "pred_history", "pred_persistence").write_csv(f"{work}/week_{name}.csv")
