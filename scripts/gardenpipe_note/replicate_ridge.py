"""Refit both Ridge recipes with NumPy only and compare with GardenPipe's streamed forecasts.

Run from a GardenPipe checkout after examples/weather/train.py:
    python replicate_ridge.py
"""

import numpy as np
import polars as pl

from weather_frame import CALENDAR, HISTORY, load_weather

ALPHAS = {"calendar": 1000.0, "history": 0.1}  # Chosen on the validation folds by train.py.
preds = pl.read_parquet("runs/weather/predictions.parquet").sort("issue_time")
frame = load_weather()
train = frame.filter(pl.col("year") <= 2014)
test = frame.filter(pl.col("year") >= 2015)
print("same issue times:", test["time"].to_list() == preds["issue_time"].to_list(), test.height)

for name, features in (("calendar", CALENDAR), ("history", HISTORY)):
    x = train.select(features).to_numpy()
    y = train["change_6h"].to_numpy()
    mean, scale = x.mean(0), x.std(0)
    z = (x - mean) / scale
    z_mean, y_mean = z.mean(0), y.mean()
    centered = z - z_mean
    gram = centered.T @ centered + ALPHAS[name] * np.eye(len(features))
    coef = np.linalg.solve(gram, centered.T @ (y - y_mean))
    change = ((test.select(features).to_numpy() - mean) / scale) @ coef + y_mean - z_mean @ coef
    forecast = test["T"].to_numpy() + change
    gap = np.abs(forecast - preds[f"pred_{name}"].to_numpy())
    print(f"{name}: largest gap {gap.max():.3e} degC, mean gap {gap.mean():.3e} degC")
