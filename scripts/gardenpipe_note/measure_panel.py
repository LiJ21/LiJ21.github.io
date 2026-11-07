"""One measured run on three streams per date, in a fresh process: measure_memory.py with MultiSourceLoader.

    PYTHONPATH=CHECKOUT python measure_panel.py --data DIR --rows ROWS_PER_DATE --days DAYS --files shared|each

The data must already exist: panel_data.py writes it in a separate process. The model predicts station A
from its own ticks, with features from all three stations.
"""

import argparse, hashlib, json
from pathlib import Path
import polars as pl
import gardenpipe.data
from gardenpipe.buffered import BufferConfig, buffered_wrapper
from gardenpipe.data import FeatureLoader, MultiSourceLoader, expand_dates
from gardenpipe.features import EwmaFeature
from gardenpipe.model import RidgeAdapter
from gardenpipe.pipeline import Pipeline
from gardenpipe.score import r2

from run_record import Stopwatch

LABELS = ["A", "B", "C"]

ap = argparse.ArgumentParser()
ap.add_argument("--data", type=Path, required=True)
ap.add_argument("--rows", type=int, required=True)
ap.add_argument("--days", type=int, required=True)
ap.add_argument("--files", choices=["shared", "each"], required=True)
ap.add_argument("--batch", type=int, default=100_000)
ap.add_argument("--buffer-mib", type=float, default=64)
ap.add_argument("--workers", type=int, default=2)
ap.add_argument("--horizon", default="5m", help="how far ahead the target looks")
ap.add_argument("--tag", default="")
ap.add_argument("--page-cache", default="unknown", help="cold or warm, as set by page_cache.py")
ap.add_argument("--out", type=Path)
a = ap.parse_args()

dates = expand_dates("20260105-20271231")[: a.days]
assert len(dates) == a.days, len(dates)
k = max(1, len(dates) // 5)
template = "panel_{date}.parquet" if a.files == "shared" else "{source}_{date}.parquet"
base = FeatureLoader(
    path=f"{a.data}/{template}",
    feature_exprs={"level": pl.col("level")},
    stateful_features=(EwmaFeature("level_ewm_1m", pl.col("level"), half_life="1m"),),
    targets={"forward_change": pl.col("level")},
    horizons=a.horizon,
)
loader = MultiSourceLoader(
    LABELS,
    base,
    label_col="station" if a.files == "shared" else None,
    tick_col="tick",
    feature_exprs={"difference": pl.col("a__level") - pl.col("b__level")},
)
features = ["a__level", "a__level_ewm_1m", "b__level_ewm_1m", "c__level_ewm_1m", "difference"]
keep = pl.col("a__tick") & pl.col("a__forward_change").is_not_null() & pl.all_horizontal(pl.col(features).is_not_null())
pipe = Pipeline(
    rolling_dates=[dates[: 2 * k], dates[2 * k : 3 * k], dates[3 * k : 4 * k]],
    test_dates=dates[4 * k :],
    adapter=RidgeAdapter(batch_size=a.batch, streaming=True),
    target="a__forward_change",
    features=features,
    data_loader=loader,
    train_sampler=(keep,),
    val_sampler=(keep,),
    test_sampler=(keep,),
    val_score=r2,
    score_direction="maximize",
    n_trials=1,
    data_source_wrapper=buffered_wrapper(BufferConfig(workers=a.workers, max_buffer_bytes=int(a.buffer_mib * 2**20))),
)
clock = Stopwatch()
pipe.train()
res = pipe.test(score=r2, keep_predictions=False)
measured = clock.record()
out = dict(
    tag=a.tag,
    files=a.files,
    horizon=a.horizon,
    rows=a.rows,
    days=a.days,
    batch=a.batch,
    buffer_mib=a.buffer_mib,
    workers=a.workers,
    page_cache=a.page_cache,
    loader_sha=hashlib.sha256(Path(gardenpipe.data.__file__).read_bytes()).hexdigest()[:12],
    **measured,
    test_r2=float(res["test_score"]),
    test_n=int(res["n"]),
    coef=[float(x) for x in pipe.model.coef],
    intercept=float(pipe.model.intercept),
)
line = json.dumps(out)
print(line)
if a.out:
    with a.out.open("a") as f:
        f.write(line + "\n")
