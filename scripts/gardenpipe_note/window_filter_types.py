"""Do the published and the patched window filters keep the same rows?

Calls the real FeatureLoader._filter_window from the checkout on PYTHONPATH and
compares it with the published expression, for each column type, on a frame and
on a Parquet scan, at every boundary that matters: each time, and just either
side of it, including before 1970 and sub-unit offsets. The boundaries are wider
than real windows give: a real end is a time in the column plus a horizon, so it
is never negative. loader_column_types.py runs the loader itself.

    PYTHONPATH=CHECKOUT python window_filter_types.py SCRATCH_DIR
"""
import hashlib, sys, tempfile, types
from pathlib import Path
import polars as pl
import gardenpipe.data as gd

print("polars", pl.__version__, "| data.py", hashlib.sha256(Path(gd.__file__).read_bytes()).hexdigest()[:12])

NS_DAY = 86_400_000_000_000
EPOCHS = {"before-1970": -40 * NS_DAY - 1_234_567_891, "around-1970": -NS_DAY // 2, "2024": 19_800 * NS_DAY + 987_654_321}
STEPS = [0, 1, 999, 1_000, 1_500, 999_999, 1_000_000, 1_500_000, 2 * 10**9, 3_600 * 10**9, NS_DAY, NS_DAY + 7, 3 * NS_DAY]
DTYPES = [
    pl.Datetime("ns"), pl.Datetime("us"), pl.Datetime("ms"),
    pl.Datetime("ns", "UTC"), pl.Datetime("us", "UTC"), pl.Datetime("ms", "UTC"),
    pl.Datetime("ns", "Europe/Amsterdam"), pl.Datetime("us", "Asia/Tokyo"), pl.Datetime("ms", "America/New_York"),
    pl.Date, pl.Int64, pl.Int32, pl.UInt64, pl.Float64, pl.String,
]

def frame(base, dtype):
    ns = pl.Series("t", sorted({base + s for s in STEPS}), dtype=pl.Int64)
    df = pl.DataFrame({"t": ns})
    if dtype == pl.String:
        return df.select(pl.col("t").cast(pl.Datetime("ns")).dt.to_string("%Y-%m-%dT%H:%M:%S%.f"))
    if isinstance(dtype, pl.Datetime) or dtype == pl.Datetime:
        out = pl.col("t").cast(pl.Datetime("ns"))
        if dtype.time_zone:
            out = out.dt.replace_time_zone("UTC").dt.convert_time_zone(dtype.time_zone)
        return df.select(out.cast(dtype))
    if dtype == pl.Date:
        return df.select(pl.col("t").cast(pl.Datetime("ns")).cast(pl.Date)).unique(maintain_order=True)
    if dtype in (pl.Int32, pl.UInt64):
        return df.select((pl.col("t") - base).clip(0, 2**31 - 1) .cast(dtype))
    return df.select(pl.col("t").cast(dtype))

def old(lf, x):
    return lf.filter((pl.col("__load_row") >= 0) & (gd._epoch_ns("t") <= x))

def new(lf, x):
    stub = types.SimpleNamespace(target_time="t")
    return gd.FeatureLoader._filter_window(stub, lf, (0, None, x, 0, 0, None))

def run(q, engine):
    try:
        return q.collect(engine=engine).get_column("__load_row").to_list(), None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e).splitlines()[0][:90]}"

tmp = Path(tempfile.mkdtemp(dir=sys.argv[1]))
summary = {}
for dtype in DTYPES:
    key = str(dtype)
    tally = summary.setdefault(key, dict(cases=0, same=0, differ=0, old_err=0, new_err=0, example=None, olderr=None, newerr=None))
    for label, base in EPOCHS.items():
        try:
            df = frame(base, dtype).with_row_index("__load_row")
        except Exception as e:
            tally["example"] = f"could not build: {e}"
            continue
        try:
            physical = df.select(gd._epoch_ns("t")).to_series().to_list()
        except Exception:
            physical = [base + s for s in STEPS]
        boundaries = sorted({v + d for v in physical for d in (-1_500_000, -1_000, -1, 0, 1, 1_000, 1_500_000)})
        path = tmp / f"{abs(hash((key, label)))}.parquet"
        df.write_parquet(path, statistics=True, row_group_size=2)
        for source, make in (("memory", df.lazy), ("parquet", lambda: pl.scan_parquet(path))):
            for engine in ("in-memory", "streaming"):
                for x in boundaries:
                    a, ea = run(old(make(), x), engine)
                    b, eb = run(new(make(), x), engine)
                    tally["cases"] += 1
                    if ea and eb: tally["old_err"] += 1; tally["new_err"] += 1; tally["olderr"] = ea; tally["newerr"] = eb
                    elif ea: tally["old_err"] += 1; tally["olderr"] = ea
                    elif eb: tally["new_err"] += 1; tally["newerr"] = eb
                    elif a == b: tally["same"] += 1
                    else:
                        tally["differ"] += 1
                        tally["example"] = tally["example"] or f"{label} {source}/{engine} x={x}: old {a} new {b}"

for key, t in summary.items():
    flag = "ok  " if t["differ"] == 0 and t["new_err"] <= t["old_err"] else "DIFF"
    print(f"{flag} {key:44s} cases {t['cases']:5d} same {t['same']:5d} differ {t['differ']:4d} old-err {t['old_err']:4d} new-err {t['new_err']:4d}")
    for k in ("example", "olderr", "newerr"):
        if t[k]: print(f"       {k}: {t[k]}")
