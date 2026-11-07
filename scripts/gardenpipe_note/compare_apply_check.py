"""Summarize apply_check.sh output.

    python compare_apply_check.py OUT/before OUT/after     peak and time per job, then how far the results moved
    python compare_apply_check.py OUT/batch/runs.jsonl     the runs of the batch, slope or panel phase, by setting

The first form needs Polars.
"""

import json
import sys
from pathlib import Path

if len(sys.argv) == 2:
    runs = [json.loads(line) for line in open(sys.argv[1])]
    print(f"{'mode':12s} {'setting':10s} {'rows':>5s} {'loader':13s} {'peaks, MiB':18s} {'times, s':16s} {'test R2':8s}")
    groups = {}
    for run in runs:
        groups.setdefault((run.get("mode", run.get("files")), run["tag"].split(":")[1], run["rows"] // 10**6), []).append(run)
    for (mode, setting, rows), group in groups.items():
        peaks = [round(run["peak_rss_mib"]) for run in group]
        times = [round(run["seconds"], 1) for run in group]
        print(f"{mode:12s} {setting:10s} {rows:4d}M {group[0]['loader_sha']:13s} {str(peaks):18s} {str(times):16s} {group[0]['test_r2']:.13f}")
    raise SystemExit

import polars as pl

before, after = map(Path, sys.argv[1:3])


def timed(directory, name):
    peak_kib, seconds = (directory / f"{name}.time").read_text().split()[-2:]
    return int(peak_kib) / 1024, float(seconds)


def score_line(directory, name):
    with open(directory / f"{name}.log", errors="ignore") as log:
        return next(line.strip() for line in log if line.startswith("test R^2"))


print(f"{'job':20s} {'before MiB':>10s} {'after MiB':>10s} {'before s':>9s} {'after s':>8s}")
for name in ("minimal_10_warm", "minimal_30_warm", "minimal_10_cold", "weather_5000", "weather_20000", "weather_1000000"):
    (peak_b, time_b), (peak_a, time_a) = timed(before, name), timed(after, name)
    print(f"{name:20s} {peak_b:10.0f} {peak_a:10.0f} {time_b:9.1f} {time_a:8.1f}")

fixed_b = [json.loads(line) for line in open(before / "fixed.jsonl")]
fixed_a = [json.loads(line) for line in open(after / "fixed.jsonl")]
for x, y in zip(fixed_b, fixed_a):
    print(f"{'fixed ' + str(x['rows'] // 10**6) + 'M ' + x['horizon']:20s} {x['peak_rss_mib']:10.0f} {y['peak_rss_mib']:10.0f} {x['seconds']:9.1f} {y['seconds']:8.1f}")
    coef = max(abs(p - q) for p, q in zip(x["coef"], y["coef"]))
    print(f"  loader {x['loader_sha']} to {y['loader_sha']}: R2 gap {abs(x['test_r2'] - y['test_r2']):.2e}, largest coefficient gap {coef:.2e}, intercept gap {abs(x['intercept'] - y['intercept']):.2e}")

print()
for name in ("minimal_10_warm", "minimal_30_warm", "minimal_10_cold"):
    print(f"{name}: score line identical: {score_line(before, name) == score_line(after, name)} ({score_line(after, name)})")
for batch in (5000, 20000, 1000000):
    x = pl.read_parquet(before / f"weather_{batch}" / "predictions.parquet")
    y = pl.read_parquet(after / f"weather_{batch}" / "predictions.parquet")
    same = (before / f"weather_{batch}" / "validation.json").read_bytes() == (after / f"weather_{batch}" / "validation.json").read_bytes()
    print(f"weather {batch}: {x.height} predictions exactly equal: {x.equals(y)}; validation.json identical: {same}")
