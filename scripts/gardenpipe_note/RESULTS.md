# GardenPipe note: results and how to reproduce them

Everything behind the note *Arbitrarily large data, bounded memory*: the machine, the exact versions, the data, the commands, the numbers, and what went wrong on the way. Raw outputs are in `results/`.

> **Status, 5 November 2026, late evening.** Section 7, on the weather data, is final. A clean re-run of the memory experiments, from a fresh clone with pinned versions and with every run starting from a cold page cache, is in progress. The tables in section 6 are still from the first pass, whose faults are listed in section 8. They will be replaced when the run ends, so do not quote them until this notice is gone.

## 1. Environment

| | |
| --- | --- |
| CPU | Intel Core i7-12700F, 12 cores (8 performance, 4 efficiency), 20 threads |
| Memory | 31 GiB RAM (32,630,928 kB), 4 GiB swap |
| Storage | Kingston KC3000 1 TB NVMe SSD, ext4 |
| System | Ubuntu 24.04.5 LTS, Linux 7.0.0-42-generic, systemd 255, cgroup v2 |
| Kernel settings | `vm.overcommit_memory=0`, `vm.swappiness=60` |
| Python | CPython 3.12.13, uv 0.11.6 |
| Main packages | polars 2.1.0, numpy 2.5.4, xgboost 3.4.1, scikit-learn 1.9.1, scipy 1.18.1, optuna 5.0.0 |
| GardenPipe | commit `9bc5e3e7c98cd04fa104a4ef629a20137290eff6` |
| Thread settings | None set. Polars and XGBoost use all 20 threads |

GardenPipe does not track a lock file at this commit, so `results/uv.lock` records the resolved versions. Use it: a fresh `uv sync` without it can resolve newer packages. `results/environment.txt` has the full package list.

## 2. Reproduce everything

Requires Linux, [uv](https://docs.astral.sh/uv/), about 30 GiB of free disk, and 19 GiB of free RAM for the largest in-memory run.

The 1 GiB limit needs a systemd user session with the memory controller delegated. Check this first, because without delegation the limit is silently not enforced:

```sh
cat /sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers   # must list memory
```

Then, with `NOTE` set to this directory and `WORK` to a directory on a fast disk:

```sh
export NOTE=/path/to/LiJ21.github.io/scripts/gardenpipe_note
export WORK=/fast/disk/gardenpipe-note
mkdir -p "$WORK"

git clone https://github.com/LiJ21/GardenPipe && cd GardenPipe
git checkout 9bc5e3e7c98cd04fa104a4ef629a20137290eff6
cp "$NOTE/results/uv.lock" .
uv sync --frozen --extra viz --extra linear --extra xgboost

bash "$NOTE/record_environment.sh" > "$WORK/environment.txt" 2>&1
bash "$NOTE/run_weather.sh" > "$WORK/weather.log" 2>&1           # about 15 minutes
bash "$NOTE/run_experiments.sh" > "$WORK/experiments.log" 2>&1   # about 2.5 hours
python3 "$NOTE/summarize.py" "$WORK"                             # the tables in section 6
```

Both run scripts continue past a failed step, so check their logs. Keep the machine otherwise idle: every result records `other_cpu_seconds`, the CPU time everything else used during the run, and it should be small.

To redraw the figures, from the root of this repository:

```sh
.venv/bin/python scripts/gardenpipe_note/collect.py "$WORK"
.venv/bin/python scripts/draw_gardenpipe_figures.py
```

To run a single measurement, from the GardenPipe checkout (data must exist first):

```sh
.venv/bin/python "$NOTE/generate_data.py" --data "$WORK/d4m" --rows 4000000 --days 30
python3 "$NOTE/page_cache.py" cold "$WORK/d4m"
.venv/bin/python "$NOTE/measure_memory.py" --data "$WORK/d4m" --rows 4000000 --days 30 --mode stream --page-cache cold --tag try
```

GardenPipe's own tests can be run with `uv run --with pytest pytest -q`. Without torch installed, `tests/test_sample_weight.py` and `tests/test_torch_adapter_snapshots.py` fail at collection, so pass `--ignore` for both. That is unrelated to these results.

## 3. The generated data

`generate_data.py` writes one Parquet file per date, named `sensor_YYYY-MM-DD.parquet`.

- **Dates:** consecutive calendar days from 2026-01-05, weekends included: `expand_dates("20260105-20271231")[:days]`.
- **`time`:** `Datetime[ns]`, evenly spaced from midnight, with a step of 86,400 s / rows.
- **`level`:** `Float64`. Standard normal noise passed through Polars' `ewm_mean(alpha=0.005, adjust=False)` and divided by 0.005. This is an AR(1) series, x(t) = 0.995 x(t−1) + noise, with a half-life of about 138 rows, restarting at each date.
- **Random numbers:** `numpy.random.default_rng(i)`, where `i` is the date's position in the list, starting at 0.
- **Encoding:** Polars' defaults for `write_parquet`.

Each file depends only on its row count and position, so repeating generation gives identical bytes on the same versions. The SHA-256 of the first file of each dataset appears in `experiments.log`. About 10.7 bytes per row on disk: 41 MiB for a 4M-row date, 100 MiB for a 10M-row date.

| Directory | Rows per date | Dates | Rows |
| --- | ---: | ---: | ---: |
| `d4m` | 4M | 90 | 360M |
| `d10m` | 10M | 100 | 1,000M |
| `d1m`, `d2m`, `d6m`, `d8m`, `d12m`, `d16m`, `d20m` | as named | 10 | 10M to 200M |

## 4. The pipeline under test

`measure_memory.py` mirrors `examples/minimal.py` from GardenPipe, with the settings exposed.

- **Loader:** `FeatureLoader` with one plain feature `level`, one stateful feature `EwmaFeature("level_ewm_1m", col("level"), half_life="1m")`, and a five-minute forward change in `level` as the target `change_5m`. Rows with a null target are dropped.
- **Folds:** with `k = max(1, days // 5)`, rolling dates `[0:2k]`, `[2k:3k]`, `[3k:4k]`, and test dates `[4k:]`.
- **Model:** `RidgeAdapter(batch_size=B, streaming=mode == "stream")`, `n_trials=1`, no search space, so α = 1. Validation score is R².
- **Streamed mode:** `data_source_wrapper=buffered_wrapper(BufferConfig(workers=W, max_buffer_bytes=budget))`, with the other `BufferConfig` fields at their defaults, so no shuffling and `charge_dataframe=True`.
- **Materialized mode:** the control. `streaming=False` and no buffer wrapper, so each source is collected in memory. Nothing else changes.
- **Defaults:** `B` = 100,000 rows, `budget` = 64 MiB, `W` = 2.

`measure_boosting.py` uses the same loader and folds with `XGBoostAdapter(batch_size=100_000, num_boost_round=10, external_memory=flag, cache_dir=...)` and `max_depth` 4. Neither boosting mode uses the buffer wrapper.

## 5. What is measured, and how

- **Peak RSS:** `ru_maxrss` read inside the process at the end of the run. It is a high-water mark for the life of the process, including imports. Each run is a fresh process, so runs cannot inherit each other's peaks. Anything else done in that process counts too, which is the mistake described in section 8.
- **Time:** `perf_counter` around `pipe.train()` and `pipe.test()`. It excludes imports and building the loader.
- **Other CPU:** whole-machine busy time from `/proc/stat` during the run, minus this process's own CPU time. Near zero means the machine was otherwise idle.
- **Traces:** `sample_rss.py` reads `VmRSS`, `RssAnon`, and `RssFile` from `/proc/PID/status` at 5 Hz. Anonymous pages must stay in RAM. File-backed pages, such as mapped Parquet or a mapped cache, can be dropped by the kernel under pressure.
- **Hard limit:** `systemd-run --user --scope --quiet -p MemoryMax=1G -p MemorySwapMax=0`. Swap is disabled in the scope, because the machine has 4 GiB of it. RSS can sit slightly above the line, because it also counts mapped pages that the cgroup may not be charged for.
- **Page cache:** every memory run starts with its files out of the page cache. `page_cache.py cold DIR` asks the kernel to drop them with `posix_fadvise(POSIX_FADV_DONTNEED)`, which needs no root, and confirms the result with `mincore`. Data larger than RAM cannot all be cached, so cold reads are the case a bound has to cover. They raise the peak but not the time, and the `cache` runs measure the difference.

## 6. Memory results

Every table can be regenerated with `python3 summarize.py WORK_DIR`. The tag of each run is in `results.jsonl`.

**First-pass tables below: see section 8 before quoting them.** Streamed peaks at 20 dates or more, the billion-row peak, the rows-per-date series, and all timings in the first table are affected.

**Number of dates: 4M rows per date, 100,000-row batches, 64 MiB budget, two workers**

| Rows | Dates | Disk, MiB | Streamed peak, MiB | Materialized peak, MiB | Streamed, s | Materialized, s | Time ratio | R² gap | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20M | 5 | 205 | 535 | 1,477 | 24.0 | 16.3 | 1.47 | 1.1e-16 | – / – |
| 40M | 10 | 409 | 535 | 2,399 | 52.5 | 32.5 | 1.62 | 4.4e-16 | – / – |
| 80M | 20 | 818 | 626 | 4,085 | 117.4 | 88.1 | 1.33 | 3.3e-16 | – / – |
| 120M | 30 | 1,228 | 623 | 6,040 | 177.5 | 124.0 | 1.43 | 4.4e-16 | – / – |
| 240M | 60 | 2,455 | 612 | 11,923 | 347.3 | 190.4 | 1.82 | 1.1e-16 | – / – |
| 360M | 90 | 3,683 | 633 | 17,804 | 468.4 | 286.5 | 1.64 | 1.3e-15 | – / – |

Materialized fit: 48.2 MiB per million rows (4.71 GiB per 100M), intercept 380 MiB, 47.4 GiB at one billion rows.

**The same 30-day streamed job, repeated**

| Run | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| scale | 623 | 177.5 | – |
| trace | 535 | 153.0 | – |
| cap | 552 | 151.3 | – |

**Batch size: 40M rows, two workers**

| Batch rows | Budget, MiB | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: |
| 25,000 | 64 | 443 | 133.5 | – |
| 50,000 | 64 | 487 | 79.7 | – |
| 100,000 | 64 | 538 | 50.1 | – |
| 200,000 | 69 | 631 | 34.3 | – |
| 400,000 | 137 | 806 | 26.7 | – |
| 800,000 | 275 | 1,129 | 24.4 | – |
| 1,600,000 | 549 | 1,595 | 23.2 | – |

Spread of test R² across batch sizes: 8.9e-16.

**Prefetch budget: 40M rows, 100,000-row batches, two workers**

| Budget, MiB | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 16 | 527 | 58.5 | – |
| 32 | 531 | 50.9 | – |
| 64 | 533 | 50.2 | – |
| 128 | 546 | 50.4 | – |
| 256 | 546 | 50.7 | – |
| 512 | 535 | 50.7 | – |
| 1,024 | 531 | 50.6 | – |

**Workers: 40M rows, 100,000-row batches, 64 MiB budget**

| Workers | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 1 | 438 | 57.4 | – |
| 2 | 534 | 49.6 | – |
| 4 | 733 | 50.4 | – |
| 8 | 1,012 | 51.3 | – |

**Rows per date: ten dates, 100,000-row batches, 64 MiB budget, two workers**

| Rows per date | File, MiB | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 10 | 529 | – | – | 12.1 | – |
| 2M | 20 | 541 | – | – | 22.6 | – |
| 4M | 41 | 536 | – | – | 51.0 | – |
| 8M | 85 | 630 | – | – | 116.0 | – |
| 10M | 100 | 816 | – | – | 149.0 | – |
| 16M | 166 | 840 | – | – | 270.6 | – |

**Completed under the 1 GiB limit**

| Run | Rows | Disk, GiB | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cap | 120M | 1.20 | 552 | – | – | 151.3 | – |
| billion | 1,000M | 9.76 | 975 | – | – | 1,577.6 | – |

**Gradient boosting on the generated data: 4M rows per date**

| Mode | Rows | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Test R² | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| external | 40M | 1,844 | – | – | 321.3 | 0.501307 | – |
| in-core | 40M | 2,223 | – | – | 208.8 | 0.501307 | – |
| external | 120M | 4,829 | – | – | 935.6 | 0.496898 | – |
| in-core | 120M | 5,831 | – | – | 622.6 | 0.496898 | – |

**Ridge on random Fourier features, weather data**

| Random features | Seed | Inputs | X′X, MiB | α | Test MAE, °C | Test RMSE, °C | Peak RSS, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 18 | 0.00247 | 0.1 | 1.7045 | 2.2096 | 332 | 11.8 | – |
| 500 | 0 | 518 | 2.05 | 1.0 | 1.4197 | 1.8667 | 331 | 23.6 | – |
| 2,000 | 0 | 2,018 | 31.1 | 1.0 | 1.3596 | 1.7938 | 487 | 39.8 | – |
| 2,000 | 1 | 2,018 | 31.1 | 1.0 | 1.3665 | 1.8020 | 463 | 39.5 | – |
| 2,000 | 2 | 2,018 | 31.1 | 1.0 | 1.3510 | 1.7863 | 498 | 33.5 | – |
| 2,000 | 3 | 2,018 | 31.1 | 1.0 | 1.3589 | 1.7980 | 484 | 30.8 | – |
| 4,000 | 0 | 4,018 | 123 | 1.0 | 1.3464 | 1.7836 | 1,067 | 75.2 | – |

**A budget too small to work.** A 1 MiB budget at the defaults exits with status 1 after 0.2 s, before any worker starts, with this message:

```text
ValueError: max_buffer_bytes=1,048,576 is too small for batch_size=100,000: a pass needs 12,000,000 bytes for the batch the consumer holds plus a 2x claim for the next. Raise max_buffer_bytes to at least 12,000,000 or lower batch_size to at most 8,738.
```

**Materialized under the limit.** The 30-date job was killed at 21.5 s. The kernel log (`journalctl -k`) records the cause:

```text
Memory cgroup out of memory: Killed process 52581 (python) total-vm:12768900kB, anon-rss:1037268kB, file-rss:66920kB, shmem-rss:4kB, UID:1000 pgtables:5772kB oom_score_adj:200
```

`sample_rss.py` then reports exit status 247, which is −9 (SIGKILL) passed through `sys.exit`.

## 7. Weather results

These come from the final clean run. Everything in this section is printed by `run_weather.sh`, and the log is `results/weather.log`. The forecasts are deterministic: two runs on this machine gave identical predictions, with a largest difference of 0.0.

**Data.** The Jena climate archive: fourteen measurements every ten minutes from 2009 to 2016, 420,223 rows. `examples/weather/prepare.py` downloads it from `https://storage.googleapis.com/tensorflow/tf-keras-datasets/jena_climate_2009_2016.csv.zip`, checks SHA-256 `63d757501e92284a7de7cdbef0337f03b24e13ead7ac2b5b8c86a18d8e38ba5b`, and writes one Parquet file per year.

**Task.** Forecast `change_6h`, T(t + 6 h) − T(t), from every full hour. A label needs an observation at exactly six hours, all features must be present, and the first day of each year is skipped while lags and averages warm up. That leaves 17,377 test issue times, 99.5% of those in 2015 and 2016.

**Features.** The calendar recipe has nine: `T`, `p`, `rh`, `u`, `v`, `tod_sin`, `tod_cos`, `doy_sin`, `doy_cos`. The history recipe adds nine: `dT_1h`, `dT_3h`, `dT_24h`, `T18_minus_T`, `dp_3h`, `T_ewm_1h`, `T_ewm_6h`, `p_ewm_1h`, `p_ewm_6h`.

**Folds.** Train 2009–2012 and validate on 2013; train 2009–2013 and validate on 2014; refit on 2009–2014; test once on 2015–2016. Ridge searches α over 0.1, 1, 10, 100, 1,000, and 10,000, with 20,000-row batches. Inputs are standardized on the training folds.

**Forecasts**

| Forecast | α | Validation RMSE | MAE, °C | RMSE, °C | Bias, °C | MAE skill |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Persistence, T(t + 6 h) = T(t) | – | – | 3.256 | 4.295 | +0.001 | – |
| Daily persistence, T(t + 6 h) = T(t − 18 h) | – | – | 2.618 | 3.420 | +0.009 | 19.6% |
| Ridge, calendar recipe | 1,000 | 2.476 | 1.967 | 2.565 | −0.173 | 39.6% |
| Ridge, history recipe | 0.1 | 2.119 | 1.704 | 2.210 | −0.091 | 47.7% |

**Does streaming change the answer?**

| Comparison, over 17,377 forecasts | Calendar recipe, °C | History recipe, °C |
| --- | ---: | ---: |
| 5,000-row batches against 20,000 | 7.1 × 10⁻¹⁵ | 4.0 × 10⁻¹² |
| One batch per year against 20,000 | 7.1 × 10⁻¹⁵ | 5.4 × 10⁻¹² |
| NumPy-only rewrite, `replicate_ridge.py`, largest gap | 5.4 × 10⁻⁶ | 4.0 × 10⁻⁷ |
| NumPy-only rewrite, mean gap | 1.3 × 10⁻⁶ | 2.6 × 10⁻⁸ |

The rewrite selects the same 17,377 issue times. Its gap is larger than the batch gap because it reimplements the features and the solve; both are far below the archive's 0.01 °C resolution.

| Batch rows | Time, s | Peak RSS, MiB |
| --- | ---: | ---: |
| 5,000 | 45.3 | 316 |
| 20,000 | 17.1 | 302 |
| 1,000,000 | 10.9 | 295 |

**Fit of ridge with the history recipe**

| Check | Result | Script |
| --- | --- | --- |
| R² on temperature, ridge against persistence | 0.924 against 0.713 | `diagnostics.py` |
| R² on the six-hour change | 0.735 | `diagnostics.py` |
| Calibration slope and intercept | 1.003, +0.09 | `diagnostics.py` |
| RMSE, training years against test years | 2.201 against 2.210 | `yearly_error.py` |
| RMSE by year, 2009–2014 | 2.206, 2.180, 2.374, 2.218, 2.050, 2.164 | `yearly_error.py` |
| RMSE by year, 2015–2016 | 2.326, 2.085 | `yearly_error.py` |
| Error autocorrelation at 1, 3, 6, 12, 24 h | 0.860, 0.489, 0.006, 0.002, −0.050 | `diagnostics.py` |
| Weekly block bootstrap, 95%: MAE | 1.638–1.766 °C | `diagnostics.py` |
| Weekly block bootstrap, 95%: MAE skill | 44.2–50.6% | `diagnostics.py` |
| Share of squared error in the worst 1% of hours | 11.8% | `diagnostics.py` |
| Top 5% of forecasts, forecast against observed change | +7.27 against +8.71 °C | `diagnostics.py` |
| Mean error by month and issue hour, range | −2.06 (August, 06:00) to +1.38 (December, 13:00) | `diagnostics.py` |
| Same map, correlation between 2015 and 2016 | 0.810 | `model_diagnostics.py`, `figure_data.py` |

The worst forecast was issued at 07:00 on 1 June 2015, at 17.3 °C. It expected 22.2 °C at 13:00, and the station recorded 10.3 °C. `worst_forecast.py` prints the hours around it: humidity was 67.7% at issue time and 81.2% an hour later, and the wind later turned from south-southwest to northeast.

**Model comparison, same rows and folds**

| Model | Selected on validation | Test MAE, °C | Test RMSE, °C | Slope | Map correlation |
| --- | --- | ---: | ---: | ---: | ---: |
| Ridge, 18 features | α = 0.1 | 1.704 | 2.210 | 1.003 | 0.810 |
| Ridge, with season-by-hour terms (24 features) | α = 0.1 | 1.640 | 2.132 | 1.002 | 0.603 |
| Ridge, pairwise products (189 features), NumPy only | α = 0.1 | 1.493 | 1.949 | – | – |
| Gradient boosting | depth 9, η = 0.02, 272 trees | 1.333 | 1.770 | 1.002 | 0.110 |
| Boosting with season-by-hour terms | depth 9, η = 0.02, 227 trees | 1.329 | 1.768 | – | – |
| Average of boosting and 2,000 random features | – | 1.319 | – | – | – |

Boosting used `subsample` 0.8 and `colsample_bytree` 0.8, and searched depths 3, 5, 7, 9, and 11 against η of 0.02 and 0.05, with up to 5,000 rounds and early stopping after 50 rounds without improvement. The refit used the median of the selected trial's two stopping points, 220 and 323. The depth is interior to the grid. The learning rate is at the lower of the two tried: η = 0.02 beat 0.05 by 0.6% on validation RMSE, so a lower rate may gain a little more.

Boosting's test MAE is 21.8% below ridge's (weekly block bootstrap, 95%: 20.1–23.4%), and it is lower at each of the 24 issue hours and in each of the 12 months. Its validation RMSE is 1.720, and the two random-feature rows below can be compared with it on that footing: 1.755 for 2,000 features and 1.737 for 4,000.

**Ridge on random Fourier features, weather data**

| Random features | Seed | Inputs | X′X, MiB | α | Test MAE, °C | Test RMSE, °C | Peak RSS, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 18 | 0.00247 | 0.1 | 1.7045 | 2.2096 | 326 | 8.8 | 1.7 |
| 500 | 0 | 518 | 2.05 | 1.0 | 1.4197 | 1.8667 | 366 | 15.2 | 0.4 |
| 2,000 | 0 | 2,018 | 31.1 | 1.0 | 1.3596 | 1.7938 | 506 | 27.4 | 0.7 |
| 2,000 | 1 | 2,018 | 31.1 | 1.0 | 1.3665 | 1.8020 | 474 | 28.7 | 1.0 |
| 2,000 | 2 | 2,018 | 31.1 | 1.0 | 1.3510 | 1.7863 | 486 | 30.8 | 14.7 |
| 2,000 | 3 | 2,018 | 31.1 | 1.0 | 1.3589 | 1.7980 | 487 | 31.4 | 15.2 |
| 4,000 | 0 | 4,018 | 123 | 1.0 | 1.3464 | 1.7836 | 1,067 | 64.8 | 34.7 |

Random features use an RBF kernel width of γ = 0.05, chosen against 0.1 on the validation folds by `feature_width.py`. Inputs are the 18 standardized features plus the random cosines, so "Inputs" is 18 more than the feature count. Seed 0 is shown in the figure.

Gradient boosting took 20.2 s and peaked at 544 MiB on this data, in a separate process with its selected settings (`results/boosting_weather.jsonl`). The times are not strictly comparable, because ridge searches six values of α and boosting ran one fixed configuration.

## 8. Corrections to the first pass

The first pass ran on the afternoon of 5 November 2026, with the data on the same disk and the same versions. Its raw outputs are kept in `results/first-pass/`. These are the faults found in it. All were found by checking the results against the harness, and all are fixed in the scripts here.

**Data generated inside the measured process.** `measure_memory.py` used to write any missing file before measuring, in the same process, and `ru_maxrss` covers the whole process. The first pass grew its dataset as it went, so the streamed run at each new size also generated that size's new dates. The field `gen_seconds` shows it:

| Streamed run | Generated in process, s | Peak, MiB |
| --- | ---: | ---: |
| 5 dates | 0.0 | 535 |
| 10 dates | 0.0 | 535 |
| 20 dates | 1.2 | 626 |
| 30 dates | 1.7 | 623 |
| 60 dates | 3.5 | 612 |
| 90 dates | 3.5 | 633 |
| 30 dates, repeated | 0.0 | 535 |
| 30 dates, under the limit | 0.0 | 552 |

The spread of 535–633 MiB was first read as run-to-run noise. It was an artifact: without generation, the streamed peak did not depend on the number of dates. The same fault touches the billion-row run, which generated files for 36 s under the limit and reported 975 MiB, and the rows-per-date points at 1M, 2M, 8M, and 16M. Materialized runs always found their data in place, so their peaks are unaffected. Generation now has its own script, and `measure_memory.py` refuses to start if a file is missing.

**The page cache was not controlled.** This one was found late, and it also overturned part of the correction above. A clean run at 4M rows per date peaked at 697 MiB, against a steady 535 MiB before, with identical data, packages, and source. The two runs differed in whether the files were in the page cache, which depended on what had been written since. A direct test, in `results/cache-test/`, settled it. Each line is the same 40M-row job:

| Files | Peak, MiB | With the RSS sampler, MiB | Time, s |
| --- | ---: | ---: | ---: |
| Warm: read first, all resident | 548, 542, 533 | 544 | 51.6–52.2 |
| Cold: evicted first, none resident | 688, 694, 685 | 694 | 51.3–54.5 |

The same test gave 478 and 561 MiB, warm and cold, at 1M rows per date, and 626 and 806 MiB at 10M. So the sampler has no effect, and the extra memory is real, because it is anonymous. The first pass's 535 MiB was therefore a best case, seen because its files were freshly written and still cached. We did not trace which buffers hold the difference. Every run now starts cold.

**Other jobs ran during the timed runs.** From 16:24 to 16:56 CET, the weather model comparisons ran alongside the data-size grid, so those timings are too long and the time ratio is unreliable. The 30-date job took 177 s streamed and 124 s materialized in that grid, against 153 s and 95 s when run alone. The same applies to the first-pass times for random features, for weather boosting, and for `train.py` at batch sizes of 5,000 and 1,000,000. Peaks were not visibly affected: the 30-date materialized run peaked at 6,040 MiB in the grid and 6,043 MiB alone. Every record now carries `other_cpu_seconds`.

**Boosting did not run with the settings reported.** The search space contained `num_boost_round`, but that is a setting of `XGBoostAdapter`, not an XGBoost parameter. XGBoost ignored it with a warning, `Parameters: { "num_boost_round" } are not used`, and every fit used the adapter's default of 100 rounds. The model described as "800 rounds" had 100 trees, which `num_boosted_rounds()` confirmed. Its depth had also been chosen at the edge of the grid. `compare_models.py` now picks the number of rounds by early stopping on the validation folds, over a wider grid, and the refit uses the median round of the selected trial. The effect was modest, because early stopping lands near the old count at these settings, but one conclusion changed: random features come within 1–2% of boosting rather than matching it.

| Boosting | Trees | Test MAE, °C | Test RMSE, °C | MAE reduction from ridge, 95% interval |
| --- | ---: | ---: | ---: | ---: |
| First pass: depth 7, η = 0.05 | 100 | 1.3586 | 1.7970 | 20.3%, 18.6–21.9% |
| Final: depth 9, η = 0.02 | 272 | 1.3329 | 1.7695 | 21.8%, 20.1–23.4% |

**Early traces measured the wrong process.** The first grid launched `uv run python`, so the sampler read the `uv` wrapper, at about 42 MiB, instead of Python. Those traces were discarded and are not in `results/first-pass/`. Peak RSS from `ru_maxrss` was read inside Python and is unaffected. The scripts now call `.venv/bin/python` directly.

**External memory was judged by RSS alone.** Peak RSS with XGBoost's external memory rose from 1.8 GiB to 4.8 GiB when the data tripled, but RSS includes mapped cache pages that the kernel can drop. `sample_rss.py` now splits RSS into anonymous and file-backed pages, so the two can be told apart.

**Smaller errors.** The draft described a "20-core machine"; it has 12 cores and 20 threads. A figure label gave *X′X* for 18 features as 2.6 KiB; 18² × 8 bytes is 2.5 KiB.

## 9. What should match

| Quantity | What to expect on your machine |
| --- | --- |
| Generated files | Identical bytes with the pinned versions: compare the SHA-256 lines in `experiments.log` |
| Forecasts and test scores | The same to within rounding with the pinned versions, whichever machine you use. BLAS and thread count can move the last few digits |
| Streamed against materialized R² | Agree to about 10⁻¹⁵ |
| Peak RSS, shape | Flat in the number of dates, rising with batch size and workers |
| Peak RSS, size | Depends on thread count and allocator: Polars sizes its pools from the number of threads, so expect different constants on a different CPU count |
| Time | Depends on the machine. Ratios travel better than seconds |
| Under the 1 GiB limit | Streamed finishes and materialized is killed, as long as the streamed peak on your machine stays below the limit |

## 10. Files

| Path | Contents |
| --- | --- |
| `results/uv.lock` | Exact package versions, to copy into the GardenPipe checkout |
| `results/environment.txt` | Machine, kernel settings, and full package list for the clean run |
| `results/results.jsonl` | One line per memory run, with every setting and result |
| `results/rff.jsonl`, `results/boosting_weather.jsonl` | Time, memory, and error by model on the weather data |
| `results/weather.log`, `results/experiments.log` | Complete output of the two run scripts, with timestamps |
| `results/failfast.log` | The rejected budget and its message |
| `results/cache-test/` | The warm and cold comparison that found the page-cache effect |
| `results/rss/` | RSS traces, as `t,rss_mib,anon_mib,file_mib` |
| `results/first-pass/` | The superseded first pass, kept for section 8 |
