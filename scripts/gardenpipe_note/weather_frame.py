"""One full in-memory pass over the Jena files, with no GardenPipe code."""

from pathlib import Path

import numpy as np
import polars as pl

CALENDAR = ["T", "p", "rh", "u", "v", "tod_sin", "tod_cos", "doy_sin", "doy_cos"]
HISTORY = CALENDAR + ["dT_1h", "dT_3h", "dT_24h", "T18_minus_T", "dp_3h"]
HISTORY += [f"{c}_ewm_{h}" for c in ("T", "p") for h in ("1h", "6h")]


def _year(path: Path, year: int) -> pl.DataFrame:
    d = pl.read_parquet(path).sort("time")

    def lag(col: str, hours: int) -> pl.Series:
        earlier = d.select("time", pl.col(col).alias("v"))
        earlier = earlier.with_columns(pl.col("time") + pl.duration(hours=hours))
        return d.select("time").join(earlier, on="time", how="left")["v"]

    minutes = pl.col("time").dt.hour().cast(pl.Int32) * 60 + pl.col("time").dt.minute().cast(pl.Int32)
    day = minutes / 1440 * (2 * np.pi)
    season = (pl.col("time").dt.ordinal_day() - 1) / 365.25 * (2 * np.pi)
    wind = pl.col("wd").radians()
    f = d.with_columns(
        u=pl.col("wv") * wind.cos(),
        v=pl.col("wv") * wind.sin(),
        tod_sin=day.sin(),
        tod_cos=day.cos(),
        doy_sin=season.sin(),
        doy_cos=season.cos(),
        T_1=lag("T", 1),
        T_3=lag("T", 3),
        T_18=lag("T", 18),
        T_24=lag("T", 24),
        p_3=lag("p", 3),
    ).with_columns(
        dT_1h=pl.col("T") - pl.col("T_1"),
        dT_3h=pl.col("T") - pl.col("T_3"),
        dT_24h=pl.col("T") - pl.col("T_24"),
        T18_minus_T=pl.col("T_18") - pl.col("T"),
        dp_3h=pl.col("p") - pl.col("p_3"),
        **{
            f"{c}_ewm_{h}": pl.col(c).ewm_mean_by("time", half_life=h)
            for c in ("T", "p")
            for h in ("1h", "6h")
        },
    )
    future = d.select((pl.col("time") - pl.duration(hours=6)).alias("time"), pl.col("T").alias("T_6h"))
    return f.join(future, on="time", how="left").with_columns(
        change_6h=pl.col("T_6h") - pl.col("T"), year=pl.lit(year)
    )


def load_weather(root: str | Path = ".") -> pl.DataFrame:
    """Eligible hourly rows for 2009-2016, in time order, with features and the label."""

    root = Path(root)
    frames = [_year(root / f"data/jena/jena_{y}.parquet", y) for y in range(2009, 2017)]
    need = [*HISTORY, "T_18", "change_6h"]
    return (
        pl.concat(frames, how="diagonal_relaxed")
        .filter(
            (pl.col("time").dt.minute() == 0)
            & (pl.col("time").dt.second() == 0)
            & (pl.col("time").dt.ordinal_day() > 1)
            & pl.all_horizontal(pl.col(c).is_not_null() for c in need)
        )
        .sort("time")
    )
