"""Where a materialized split's memory goes: RSS and peak at each step inside materialize().

The materialized job of measure_memory.py, with the steps timed from inside:

    PYTHONPATH=CHECKOUT python materialize_steps.py DATA_DIR DATES [MIN_ROWS]

Each step's peak is read from VmHWM, which clear_refs resets between steps. A rise is
that peak over the RSS at the end of the step before, per row of the split.
"""
import sys
import weakref
from pathlib import Path
import polars as pl
import gardenpipe.data as gd
from gardenpipe.data import FeatureLoader, expand_dates
from gardenpipe.features import EwmaFeature
from gardenpipe.model import RidgeAdapter
from gardenpipe.pipeline import Pipeline
from gardenpipe.score import r2

data, days = Path(sys.argv[1]), int(sys.argv[2])
min_rows = int(sys.argv[3]) if len(sys.argv) > 3 else 500_000
def rss(): return int(open("/proc/self/statm").read().split()[1]) * 4096 / 2**20
def hwm(): return next(int(l.split()[1]) for l in open("/proc/self/status") if l.startswith("VmHWM")) / 1024
def reset(): open("/proc/self/clear_refs", "w").write("5")
log = []
facts = []
alive = []  # weak references to each split's context array
n_rows = [0]
def mark(step):
    log.append((step, rss(), hwm(), n_rows[0], sum(ref() is not None for ref in alive)))
    reset()

orig_mat, orig_batch, orig_ctx = gd.DataSource.materialize, gd._to_batch, gd._ctx_from_df
def materialize(self):
    mark("--- start of materialize")
    out = orig_mat(self)
    mark("ctx built, batch returned")
    return out
def to_batch(df, *a, **k):
    if df.height >= min_rows:
        n_rows[0] = df.height
        sizes = {c: round(df[c].estimated_size() / df.height, 1) for c in df.columns}
        facts.append(f"frame itself: {df.estimated_size() / df.height:.0f} B/row {sizes}")
        mark(f"frame collected ({df.width} cols)")
    return orig_batch(df, *a, **k)
def ctx(df):
    big = df.height >= min_rows
    if big: mark("x and y converted to NumPy")
    out = orig_ctx(df)
    if big:
        vals = out["date"]
        alive.append(weakref.ref(vals))
        facts.append(f"ctx: date dtype {vals.dtype}, distinct objects in first 1000: {len({id(v) for v in vals[:1000]})}, "
                     f"one object {sys.getsizeof(vals[0])} B, pointer array {vals.nbytes / len(vals):.0f} B/row; "
                     f"tag first value {out['tag'][0]!r}, distinct objects in first 1000: {len({id(v) for v in out['tag'][:1000]})}; "
                     f"dates list {out['dates'][:2]} tags list {out['tags'][:2]}")
    return out
gd.DataSource.materialize = materialize
gd._to_batch = to_batch
gd._ctx_from_df = ctx

dates = expand_dates("20260105-20261231")[:days]
k = max(1, len(dates) // 5)
loader = FeatureLoader(path=f"{data}/sensor_{{date}}.parquet", feature_exprs={"level": pl.col("level")},
    stateful_features=(EwmaFeature("level_ewm_1m", pl.col("level"), half_life="1m"),),
    targets={"forward_change": pl.col("level")}, horizons="5m")
keep = pl.col("forward_change").is_not_null()
pipe = Pipeline(rolling_dates=[dates[:2*k], dates[2*k:3*k], dates[3*k:4*k]], test_dates=dates[4*k:],
    adapter=RidgeAdapter(batch_size=100_000, streaming=False), target="forward_change",
    features=["level", "level_ewm_1m"], data_loader=loader, train_sampler=(keep,), val_sampler=(keep,),
    test_sampler=(keep,), val_score=r2, score_direction="maximize", n_trials=1)
pipe.train()
mark("end of train()")
pipe.test(score=r2, keep_predictions=False)
mark("end of test()")
prev = None
print(f"{'step':40s} {'RSS MiB':>8s} {'peak in step':>12s} {'rise B/row':>11s} {'ctx arrays alive':>17s}")
for step, r, h, n, held in log:
    rise = f"{(h - prev) * 2**20 / n:8.0f}" if prev is not None and n else ""
    print(f"{step[:40]:40s} {r:8.0f} {h:12.0f} {rise:>11s} {held:17d}")
    prev = r
print()
for f in facts: print(f)
