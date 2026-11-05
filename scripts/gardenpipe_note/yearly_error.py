"""Ridge error by year: training years against test years, with no GardenPipe code.

Run from a GardenPipe checkout: python yearly_error.py
"""

import numpy as np

from weather_frame import HISTORY, load_weather

frame = load_weather()
years = frame["year"].to_numpy()
x = frame.select(HISTORY).to_numpy()
y = frame["change_6h"].to_numpy()
train = years <= 2014
mean, scale = x[train].mean(0), x[train].std(0)
z = (x - mean) / scale
z_mean, y_mean = z[train].mean(0), y[train].mean()
centered = z[train] - z_mean
coef = np.linalg.solve(centered.T @ centered + 0.1 * np.eye(z.shape[1]), centered.T @ (y[train] - y_mean))
error = z @ coef + y_mean - z_mean @ coef - y
for year in range(2009, 2017):
    i = years == year
    print(year, i.sum(), round(float(np.sqrt((error[i] ** 2).mean())), 3), round(float(np.abs(error[i]).mean()), 3))
print("train RMSE", np.sqrt((error[train] ** 2).mean()), "test RMSE", np.sqrt((error[~train] ** 2).mean()))
