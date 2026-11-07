# GardenPipe note: results and how to reproduce them

Everything behind the note *Arbitrarily large data, bounded memory*: the machine, the exact versions, the data, the commands, the numbers, and what went wrong on the way. Raw outputs are in `results/`.

The memory experiments were run twice: on GardenPipe as published at commit `9bc5e3e`, and on the same commit with two small patches that came out of this work. Section 6 holds the published code's results, section 7 explains why the patches exist, and section 8 holds the full grid with both patches. The tables in the note come from section 8. Both patches are now on GardenPipe's `main`, with a small guard on top, at `89d7244` (section 13).

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
| GardenPipe | commit `9bc5e3e7c98cd04fa104a4ef629a20137290eff6`, without and with `window-filter.patch` and `time-chunks.patch` |
| Thread settings | None set. Polars and XGBoost use all 20 threads |

GardenPipe does not track a lock file at this commit, so `results/uv.lock` records the resolved versions. Use it: a fresh `uv sync` without it can resolve newer packages. `results/environment.txt` has the full package list.

## 2. Reproduce everything

Requires Linux, [uv](https://docs.astral.sh/uv/), about 36 GiB of free disk, and 19 GiB of free RAM for the largest in-memory run.

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
bash "$NOTE/run_followups.sh" > "$WORK/followup.log" 2>&1        # about 2.5 hours
bash "$NOTE/run_followups.sh" slow_stream slow_epoch slow_epoch_threads slow_stream_threads chunk_query limit_before >> "$WORK/followup.log" 2>&1   # about 40 minutes
python3 "$NOTE/summarize.py" "$WORK"                             # the tables in sections 6 and 7
```

The patched measurements need three more checkouts of the same commit: one with the window filter alone, one with both patches, and one with a third patch that was tested and not adopted.

```sh
cd ..
for name in filter both wide; do
  git clone -q GardenPipe "$name"
  git -C "$name" checkout -q 9bc5e3e7c98cd04fa104a4ef629a20137290eff6
  git -C "$name" apply "$NOTE/window-filter.patch"
  cp "$NOTE/results/uv.lock" "$name"
done
git -C both apply "$NOTE/time-chunks.patch"
git -C wide apply "$NOTE/time-chunks.patch"
git -C wide apply "$NOTE/larger-time-chunks.patch"
cp -r GardenPipe/data both/                        # keeps the weather data from being downloaded again

cd filter
uv sync --frozen --extra viz --extra linear --extra xgboost
bash "$NOTE/run_followups.sh" fix_curve fix_flat >> "$WORK/followup.log" 2>&1     # about 40 minutes

cd ../both
uv sync --frozen --extra viz --extra linear --extra xgboost
bash "$NOTE/run_followups.sh" chunk_flat chunk_curve chunk_threads chunk_changes chunk_budget chunk_repeats \
  chunk_boosting chunk_billion limit_after >> "$WORK/followup.log" 2>&1            # about 2 hours

cd ../wide
uv sync --frozen --extra viz --extra linear --extra xgboost
bash "$NOTE/run_followups.sh" chunk_wide >> "$WORK/followup.log" 2>&1              # about 20 minutes

# The same job from each checkout in turn, so that drift between hours cannot pass for a patch. About 40 minutes.
cd ..
for order in "GardenPipe filter both" "filter both GardenPipe" "both GardenPipe filter" \
             "filter both wide" "both wide filter" "wide filter both"; do
  for name in $order; do
    (cd "$name" && bash "$NOTE/run_followups.sh" rotation >> "$WORK/followup.log" 2>&1)
  done
done

# The full grids again, unchanged, from the checkout with both patches, in a directory of their own that shares the data.
cd both
export PATCHED=/fast/disk/gardenpipe-note-patched
mkdir -p "$PATCHED"
for dir in "$WORK"/d*m; do ln -s "$dir" "$PATCHED/"; done
WORK=$PATCHED bash "$NOTE/record_environment.sh" > "$PATCHED/environment.txt" 2>&1
WORK=$PATCHED bash "$NOTE/run_weather.sh" > "$PATCHED/weather.log" 2>&1
WORK=$PATCHED bash "$NOTE/run_experiments.sh" > "$PATCHED/experiments.log" 2>&1
python3 "$NOTE/summarize.py" "$PATCHED"            # the tables in section 8
```

The run scripts continue past a failed step, so check their logs. Keep the machine otherwise idle: every result records `other_cpu_seconds`, the CPU time everything else used during the run, and it should be small. `run_followups.sh` also waits for an idle machine before each run and repeats a run that was disturbed.

To redraw the figures, from the root of this repository:

```sh
.venv/bin/python scripts/gardenpipe_note/collect.py "$PATCHED" "$WORK"
.venv/bin/python scripts/draw_gardenpipe_figures.py
```

The raw outputs in `results/` are enough to regenerate every table and figure without running anything:

```sh
python3 scripts/gardenpipe_note/summarize.py scripts/gardenpipe_note/results           # sections 6 and 7
python3 scripts/gardenpipe_note/summarize.py scripts/gardenpipe_note/results/patched   # section 8
.venv/bin/python scripts/gardenpipe_note/collect.py scripts/gardenpipe_note/results/patched scripts/gardenpipe_note/results
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

Each file depends only on its row count and position, so repeating generation gives identical bytes on the same versions. The SHA-256 of the first file of each dataset appears in `experiments.log` and, for `d40m` and `d80m`, in `followup.log`. About 10.7 bytes per row on disk: 41 MiB for a 4M-row date, 100 MiB for a 10M-row date.

| Directory | Rows per date | Dates | Rows |
| --- | ---: | ---: | ---: |
| `d4m` | 4M | 90 | 360M |
| `d10m` | 10M | 100 | 1,000M |
| `d1m`, `d2m`, `d6m`, `d8m`, `d12m`, `d16m`, `d20m` | as named | 10 | 10M to 200M |
| `d40m`, `d80m` | as named | 5 | 200M, 400M |

## 4. The pipeline under test

`measure_memory.py` mirrors `examples/minimal.py` from GardenPipe, with the settings exposed.

- **Loader:** `FeatureLoader` with one plain feature `level`, one stateful feature `EwmaFeature("level_ewm_1m", col("level"), half_life="1m")`, and a forward change in `level` as the target `forward_change`, over five minutes unless `--horizon` says otherwise. Rows with a null target are dropped.
- **Folds:** with `k = max(1, days // 5)`, rolling dates `[0:2k]`, `[2k:3k]`, `[3k:4k]`, and test dates `[4k:]`.
- **Model:** `RidgeAdapter(batch_size=B, streaming=mode == "stream")`, `n_trials=1`, no search space, so α = 1. Validation score is R².
- **Streamed mode:** `data_source_wrapper=buffered_wrapper(BufferConfig(workers=W, max_buffer_bytes=budget))`, with the other `BufferConfig` fields at their defaults, so no shuffling and `charge_dataframe=True`.
- **Materialized mode:** the control. `streaming=False` and no buffer wrapper, so each source is collected in memory. Nothing else changes.
- **Defaults:** `B` = 100,000 rows, `budget` = 64 MiB, `W` = 2.
- **No model:** `--model discard` swaps ridge for `DiscardAdapter`, which pulls every training batch and drops it, so that only the loader remains. `--consume-ms` makes it hold each batch for that long.

`measure_boosting.py` uses the same loader and folds with `XGBoostAdapter(batch_size=100_000, num_boost_round=10, external_memory=flag, cache_dir=...)` and `max_depth` 4. Neither boosting mode uses the buffer wrapper.

`reader_memory.py` is Polars alone, with no GardenPipe: one query over one file, in a fresh process.

**The patches.** Both change only `gardenpipe/data.py`, in `FeatureLoader`, and section 7 explains them. `window-filter.patch` writes the upper bound of each window on the bare time column. `time-chunks.patch`, applied after it, reads the time column in one short query per chunk instead of one query held open across the date. `larger-time-chunks.patch` was tested on top of those two and not adopted: section 8 says why. GardenPipe's own test suite gives 190 passed at every stage.

## 5. What is measured, and how

- **Peak RSS:** `ru_maxrss` read inside the process at the end of the run. It is a high-water mark for the life of the process, including imports. Each run is a fresh process, so runs cannot inherit each other's peaks. Anything else done in that process counts too, which is the mistake described in section 10.
- **Time:** `perf_counter` around `pipe.train()` and `pipe.test()`. It excludes imports and building the loader.
- **Other CPU:** whole-machine busy time from `/proc/stat` during the run, minus this process's own CPU time. Near zero means the machine was otherwise idle.
- **Traces:** `sample_rss.py` reads `VmRSS`, `RssAnon`, and `RssFile` from `/proc/PID/status` at 5 Hz. Anonymous pages must stay in RAM. File-backed pages, such as mapped Parquet or a mapped cache, can be dropped by the kernel under pressure.
- **Hard limit:** `systemd-run --user --scope --quiet -p MemoryMax=1G -p MemorySwapMax=0`. Swap is disabled in the scope, because the machine has 4 GiB of it. RSS can sit slightly above the line, because it also counts mapped pages that the cgroup may not be charged for.
- **An idle machine:** before each run, `run_followups.sh` calls `quiet.py wait`, which returns after 30 s with less than one core busy. After each run, `quiet.py keep` files the record under `results_followup.jsonl` if everything else used less than one core on average, or under `contaminated.jsonl` if not, and the run is repeated. Three runs were rejected, all because of an unrelated compile job on the same machine.
- **Settings:** each record stores the `POLARS_*` and `_RJEM_*` variables in force. Polars writes `_RJEM_MALLOC_CONF` itself on import.
- **Which code:** later records carry `loader_sha`, the first 12 hex digits of the SHA-256 of `gardenpipe/data.py`: `7c64551632de` for the published commit, `3eb3b1aaf173` with the window filter, `be906867b2f2` with both patches, and `278db29cd861` with the third. Records without the field are from the published commit, apart from the boosting records, which `measure_boosting.py` writes without it and whose tags say which code ran.
- **Page cache:** every memory run starts with its files out of the page cache. `page_cache.py cold DIR` asks the kernel to drop them with `posix_fadvise(POSIX_FADV_DONTNEED)`, which needs no root, and confirms the result with `mincore`. Data larger than RAM cannot all be cached, so cold reads are the case a bound has to cover. They raise the peak by about 150 MiB here and the time by 3–10%, and the `cache` runs measure the difference.

## 6. Memory results for the published code

Every table can be regenerated with `python3 summarize.py WORK_DIR`. The tag of each run is in `results.jsonl`.

These are the results for GardenPipe as published, from the clean run: a fresh clone, pinned versions, and every run starting from a cold page cache. All 54 records finished without a traceback. Importing the libraries alone peaks at 61.5 MiB.

**Number of dates: 4M rows per date, 100,000-row batches, 64 MiB budget, two workers**

| Rows | Dates | Disk, MiB | Streamed peak, MiB | Materialized peak, MiB | Streamed, s | Materialized, s | Time ratio | R² gap | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20M | 5 | 205 | 670 | 1,589 | 26.8 | 17.0 | 1.58 | 1.1e-16 | 2.4 / 2.0 |
| 40M | 10 | 409 | 687 | 2,423 | 51.7 | 33.7 | 1.54 | 4.4e-16 | 0.3 / 5.3 |
| 80M | 20 | 818 | 690 | 4,200 | 105.9 | 67.9 | 1.56 | 3.3e-16 | 33.4 / 49.6 |
| 120M | 30 | 1,228 | 726 | 6,129 | 156.8 | 100.7 | 1.56 | 4.4e-16 | 23.7 / -0.0 |
| 240M | 60 | 2,455 | 730 | 11,961 | 308.4 | 201.9 | 1.53 | 1.1e-16 | 18.8 / 14.4 |
| 360M | 90 | 3,683 | 722 | 16,529 | 471.4 | 312.5 | 1.51 | 1.1e-15 | 40.4 / 11.4 |

Materialized fit: 44.8 MiB per million rows (4.37 GiB per 100M), intercept 723 MiB, 44.4 GiB at one billion rows.

**The same 30-day streamed job, repeated**

| Run | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| scale | 726 | 156.8 | 23.7 |
| repeat | 719 | 155.3 | -3.4 |
| repeat | 712 | 156.9 | 34.8 |
| repeat | 703 | 156.2 | 22.9 |
| cap | 732 | 156.8 | -0.1 |

**Batch size: 40M rows, two workers**

| Batch rows | Budget, MiB | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: |
| 25,000 | 64 | 575 | 142.7 | 6.0 |
| 50,000 | 64 | 632 | 82.8 | 1.4 |
| 100,000 | 64 | 685 | 51.2 | 1.2 |
| 200,000 | 69 | 722 | 34.9 | 3.7 |
| 400,000 | 137 | 927 | 27.5 | 5.3 |
| 800,000 | 275 | 1,187 | 25.6 | 10.1 |
| 1,600,000 | 549 | 1,599 | 23.6 | 3.9 |

Spread of test R² across batch sizes: 1.0e-15.

**Prefetch budget: 40M rows, 100,000-row batches, two workers**

| Budget, MiB | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 16 | 657 | 60.3 | 1.9 |
| 32 | 686 | 52.5 | 19.2 |
| 64 | 687 | 51.5 | 5.7 |
| 128 | 686 | 51.2 | 0.9 |
| 256 | 689 | 51.8 | 6.0 |
| 512 | 682 | 52.0 | 2.9 |
| 1,024 | 689 | 51.3 | -0.7 |

**Workers: 40M rows, 100,000-row batches, 64 MiB budget**

| Workers | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 1 | 580 | 60.7 | -0.0 |
| 2 | 677 | 51.2 | 2.4 |
| 4 | 871 | 50.8 | 3.1 |
| 8 | 1,125 | 51.1 | 1.5 |

**Rows per date: ten dates, 100,000-row batches, 64 MiB budget, two workers**

| Rows per date | File, MiB | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 10 | 562 | 482 | 68 | 12.1 | 1.9 |
| 2M | 20 | 636 | 555 | 68 | 23.9 | 1.4 |
| 4M | 41 | 678 | 602 | 68 | 52.3 | 19.3 |
| 6M | 61 | 726 | 657 | 68 | 82.8 | 25.8 |
| 8M | 85 | 795 | 720 | 68 | 117.4 | 11.4 |
| 10M | 100 | 813 | 741 | 68 | 149.9 | 10.5 |
| 12M | 119 | 916 | 824 | 68 | 187.5 | 20.8 |
| 16M | 166 | 958 | 872 | 68 | 273.6 | 14.1 |
| 20M | 194 | 957 | 857 | 68 | 356.4 | 90.3 |

**Page cache: the same 40M-row job, files evicted or read first**

| Files | Runs | Lowest peak, MiB | Highest peak, MiB | Mean time, s | Most other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| cold | 3 | 680 | 697 | 52.0 | 12.9 |
| warm | 3 | 524 | 536 | 50.6 | 12.8 |

**Completed under the 1 GiB limit**

| Run | Rows | Disk, GiB | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cap | 120M | 1.20 | 732 | 662 | 67 | 156.8 | -0.1 |
| billion | 1,000M | 9.76 | 813 | 739 | 68 | 1,579.5 | 182.2 |

**Gradient boosting on the generated data: 4M rows per date**

| Mode | Rows | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Test R² | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| external | 40M | 1,849 | 1,673 | 172 | 353.7 | 0.501307 | 61.5 |
| in-core | 40M | 2,352 | – | – | 219.3 | 0.501307 | 31.3 |
| external | 120M | 4,839 | 4,669 | 172 | 1,154.6 | 0.496898 | 3515.9 |
| in-core | 120M | 5,837 | – | – | 702.3 | 0.496898 | 1086.5 |

**A budget too small to work.** A 1 MiB budget at the defaults exits with status 1 after 0.3 s, before any worker starts, with this message:

```text
ValueError: max_buffer_bytes=1,048,576 is too small for batch_size=100,000: a pass needs 12,000,000 bytes for the batch the consumer holds plus a 2x claim for the next. Raise max_buffer_bytes to at least 12,000,000 or lower batch_size to at most 8,738.
```

**Materialized under the limit.** The 30-date job was killed at about 21 s. It stayed below 570 MiB for 19 s, then went from 540 MiB to the limit in under half a second, so nothing in its early life gave warning. The kernel log (`journalctl -k`) records the cause:

```text
Memory cgroup out of memory: Killed process 101023 (python) total-vm:10463736kB, anon-rss:1037656kB, file-rss:66200kB, shmem-rss:4kB, UID:1000 pgtables:5708kB oom_score_adj:200
```

`sample_rss.py` then reports exit status 247, which is −9 (SIGKILL) passed through `sys.exit`.

**Boosting under the limit.** Both boosting modes were killed under 1 GiB on 40M rows, in-core after 48.5 s and external memory after 129.2 s. From 40M to 120M rows, peak RSS grows by about 46 bytes per row in core, and anonymous memory by about 39 with external memory. So external memory saves 17–21% of the peak at 1.6 times the time, and it is not out-of-core in the sense that streaming ridge is. The two 30-date boosting timings are inflated by that compile job, as `other_cpu_seconds` shows: 1,086 s and 3,516 s. Their peaks match the first pass to within 0.2%.

## 7. Why the peak moved with rows per date

Section 6 shows a peak that does not depend on the number of dates but rises with rows per date. This section records how the cause was found, in order, because two explanations that looked right turned out to be wrong. Every run here comes from `run_followups.sh` and is in `results_followup.jsonl`.

### 7.1 The peak rises, and it passes the limit

**Rows per date: five dates, 100,000-row batches, 64 MiB budget, two workers**

| Rows per date | Look-ahead rows | Row groups | Peak RSS, MiB | Peak anonymous, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 3,472 | 9 | 554 | 478 | 5.9 | -0.1 |
| 4M | 13,888 | 33 | 672 | – | 26.1 | 0.4 |
| 10M | 34,722 | 82 | 778 | 707 | 75.5 | 0.6 |
| 20M | 69,444 | 163 | 944 | – | 180.4 | 137.8 |
| 40M | 138,888 | 326 | 1,063 | 994 | 484.2 | 15.8 |
| 80M | 277,777 | 652 | 1,123 | 1,034 | 1,507.7 | 50.0 |

From 1M to 80M rows per date, the peak doubles and crosses 1 GiB. Time per million rows rises from 1.19 s to 3.77 s, and it fits 1.163 + 0.0324 n for n million rows per date, with R² = 0.9995. So part of the cost of a date is quadratic in its rows. Neither fact shows up when only dates are added, which is why the tables in the first half of section 6 look so good.

### 7.2 What it is not

**One change at a time: five dates, 100,000-row batches, 64 MiB budget, two workers**

| Change | Peak at 4M, MiB | Time at 4M, s | Peak at 20M, MiB | Time at 20M, s |
| --- | ---: | ---: | ---: | ---: |
| Nothing | 672 | 26.1 | 944 | 180.4 |
| No model: batches are pulled and dropped | 671 | 25.5 | 901 | 179.1 |
| Allocator returns freed memory at once | 442 | 29.4 | 682 | 191.8 |
| Read-ahead of 8 row groups | 616 | 26.4 | 826 | 184.1 |
| 4 Polars threads | 498 | 20.3 | 580 | 161.7 |
| 4 threads, read-ahead of 8 | 450 | 18.9 | 529 | 160.8 |
| 4 threads, read-ahead of 8, immediate return | 294 | 24.0 | 360 | 214.8 |

- **The model.** Replacing ridge with a loop that pulls each batch and drops it moves the peak by 1 MiB at 4M rows per date and 43 MiB at 20M.
- **The allocator.** Polars sets jemalloc's decay to `dirty_decay_ms:500,muzzy_decay_ms:1000`. Setting both to 0 removes 230 MiB at 4M and 262 MiB at 20M: a real saving, and nearly constant, so it sets the level and not the slope.
- **Look-ahead.** This was the working hypothesis, because a five-minute horizon holds 20 times as many rows at 80M per date as at 4M. It fails its test. Shortening the horizon to hold the look-ahead at 13,888 rows leaves the rise almost intact:

**Look-ahead: five dates, default settings**

| Rows per date | Horizon | Look-ahead rows | Peak RSS, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1M | 5m | 3,472 | 554 | 5.9 | -0.1 |
| 4M | 5m | 13,888 | 672 | 26.1 | 0.4 |
| 4M | 25m | 69,444 | 665 | 26.9 | -1.0 |
| 10M | 5m | 34,722 | 778 | 75.5 | 0.6 |
| 20M | 60s | 13,888 | 898 | 175.1 | 7.0 |
| 20M | 5m | 69,444 | 944 | 180.4 | 137.8 |
| 40M | 30s | 13,888 | 1,038 | 463.0 | 19.4 |
| 40M | 5m | 138,888 | 1,063 | 484.2 | 15.8 |
| 80M | 15s | 13,888 | 1,064 | 1,402.8 | 97.1 |
| 80M | 5m | 277,777 | 1,123 | 1,507.7 | 50.0 |

Thread count, on the other hand, has a strong effect at every size, which is a clue (7.4):

**Polars threads: 20M rows over five dates**

| POLARS_MAX_THREADS | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 1 | 468 | 23.5 | -0.0 |
| 2 | 423 | 19.8 | -0.2 |
| 4 | 484 | 19.5 | -0.3 |
| 8 | 549 | 21.3 | -0.4 |
| 12 | 609 | 24.7 | -1.0 |
| 20 (default) | 672 | 26.1 | 0.4 |

### 7.3 The window filter accounts for the time, not the memory

Each window is read with two bounds, in `FeatureLoader._filter_window`:

```python
(pl.col("__load_row") >= front_start) & (_epoch_ns(self.target_time) <= end_t_ns + pad_ns)
```

`_epoch_ns` is `pl.col(col).cast(pl.Datetime("ns")).dt.epoch("ns")`. Polars can compare a bare column with the minimum and maximum stored for each row group, but it cannot relate that expression to them, so the upper bound prunes nothing and only the lower bound applies. With `POLARS_VERBOSE=1`, on the 80M file, for a window starting at row 200,000:

```text
_epoch_ns(time) <= bound      Predicate pushdown: reading 650 / 651 row groups
pl.col("time") <= bound       Predicate pushdown: reading 4 / 651 row groups
```

A window in the middle of the file reads 326 of 651 groups: every window reads from its own start to the end of the date. That is the quadratic term.

`window-filter.patch` writes the same bound on the bare column, with a literal in the column's own type. The type matters. The shorter form `pl.col(t).cast(pl.Datetime("ns")) <= pl.lit(x).cast(pl.Datetime("ns"))` prunes only on naive nanosecond columns, because a cast that does anything blocks the statistics. The patched form was checked on `ns`, `us`, and `ms` columns, naive and with time zones, and it prunes on all of them and returns the same rows, including for a bound that falls between two representable values. The first measurement of this curve used the shorter form. Those six records are kept in `superseded.jsonl` (`loader_sha` `175e5cc95934`), and the table below is from a rerun with the patch as published (`3eb3b1aaf173`).

**What each patch changes: five dates, a five-minute horizon, default settings**

| Rows per date | Look-ahead rows | Pinned, MiB | Window filter, MiB | Both patches, MiB | Pinned, s | Window filter, s | Both patches, s | Largest coefficient change | R² change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 3,472 | 554 | 513 | 505 | 5.9 | 6.1 | 6.3 | 4.4e-16 | 0.0e+00 |
| 4M | 13,888 | 672 | 627 | 585 | 26.1 | 22.4 | 24.1 | 0.0e+00 | 0.0e+00 |
| 10M | 34,722 | 778 | 729 | 612 | 75.5 | 61.3 | 62.7 | 8.7e-19 | 0.0e+00 |
| 20M | 69,444 | 944 | 909 | 625 | 180.4 | 129.2 | 134.7 | 2.2e-16 | 1.1e-16 |
| 40M | 138,888 | 1,063 | 1,145 | 692 | 484.2 | 275.9 | 280.8 | 2.2e-16 | 0.0e+00 |
| 80M | 277,777 | 1,123 | 1,176 | 722 | 1,507.7 | 630.8 | 631.1 | 0.0e+00 | 0.0e+00 |

The patch takes the 80M job from 1,508 s to 631 s and moves no fitted coefficient by more than 4.4 × 10⁻¹⁶. It does not fix the peak: the filter alone takes 35–49 MiB off up to 20M rows per date, and adds 82 MiB at 40M and 53 MiB at 80M. Those differences are within what repeats can move (section 8), so the fair reading is that the rise is untouched. The first report of this finding named the filter as the likely cause of the memory rise as well, which was wrong.

### 7.4 The held-open query accounts for the memory

To cut a date into windows, `_iter_windows` takes the time column in chunks from one query, `scan().select(_epoch_ns(t)).collect_batches(...)`, held open for the whole date.

**The traces.** `rss/density5_80m.csv` is not a plateau. Memory is high through each training pass and low through each validation and test pass, and the high stretches lengthen with the training set. A worker streams one date at a time, and `_effective_workers` is `min(workers, n_dates)`, so training holds two dates open and a one-date fold holds one. Whatever costs memory is held per open date.

**Polars alone, first attempt.** `reader_memory.py` runs the stream with no GardenPipe. Its peak rises with the file, and the rise matches the compressed `time` column, 3 bytes per row, up to Polars' limit of 512 row groups:

| Rows in the file | Compressed `time` up to 512 row groups, MiB | Stream peak, MiB | Rise from the previous row, predicted and measured, MiB |
| ---: | ---: | ---: | ---: |
| 4M | 12 | 138 | |
| 20M | 57 | 190 | 46, 52 |
| 40M | 115 | 247 | 57, 57 |
| 80M | 180 | 317 | 65, 70 |

With `POLARS_ROW_GROUP_PREFETCH_SIZE=8`, the same stream stays at 110–127 MiB at every size. That looked like the answer, but it is not the whole answer. Setting that variable in the pipeline, with the look-ahead held fixed, gives 578, 816, 934, and 945 MiB at 4M, 20M, 40M, and 80M: lower, but still rising by 367 MiB.

**The mistake in that probe.** It selected the bare column, and GardenPipe selects an expression. With the expression, and the batches taken as slowly as the pipeline takes them:

**Polars alone, taking a batch of the time stream every 200 ms**

| Rows in the file | Bare column, MiB | Bare column, read-ahead of 8, MiB | GardenPipe's expression, MiB | Expression, read-ahead of 8, MiB |
| --- | ---: | ---: | ---: | ---: |
| 4M | 138 | 109 | 141 | 129 |
| 20M | 176 | 109 | 302 | 257 |
| 40M | 229 | 112 | 431 | 318 |
| 80M | 299 | 110 | 511 | 319 |

With read-ahead limited, the expression adds 20, 148, 206, and 210 MiB to the bare column at 4M, 20M, 40M, and 80M rows, and read-ahead settings do not remove it. The first two are close to the file's own decoded times at 8 bytes per row, 31 and 153 MiB. The last two are a plateau: `rss/slow_epoch_p8_40m.csv` and `rss/slow_epoch_p8_80m.csv` show it draining over the last 20–25M rows of the file at both sizes. So the engine appears to keep a limited amount of decoded data ahead of a slow consumer, and a file smaller than that limit is held almost whole. The limit depends on the thread count:

**The same stream at 40M rows, by Polars threads**

| POLARS_MAX_THREADS | Bare column, MiB | Bare column, read-ahead of 8, MiB | GardenPipe's expression, MiB | Expression, read-ahead of 8, MiB |
| --- | ---: | ---: | ---: | ---: |
| 20 (default) | 229 | 112 | 431 | 318 |
| 4 | 193 | 90 | 224 | 136 |

With four threads the expression adds 46 MiB to the bare column, against 206 MiB at the default of 20. That is 10–12 MiB per thread in both cases, so the amount kept ahead is set by the thread count, not by the file.

This accounts for three earlier observations. Thread count had a strong effect in 7.2 because the amount kept ahead scales with it: `mech-threads-4` rises by 82 MiB from 4M to 20M rows per date, against 272 MiB at the default. The rise slows down at high density because a date past the limit costs no more in this term. And the size fits: two open dates, each holding 190 MiB more at 80M than at 4M, account for almost all of the 367 MiB above. We read all of this from peaks and traces, and did not trace it in the Polars source, so "decoded data" is an inference from the sizes.

**Removing the query.** The decisive test does not depend on any of this reasoning. `time-chunks.patch` replaces the held query with one short query per chunk, `.slice(offset, chunk_size)`, which reads one or two row groups and takes about 10 ms on the 80M file. What the windowing has to carry between chunks is then one integer, the offset. With the look-ahead held at 13,888 rows:

**The same look-ahead at every density: 13,888 rows, five dates**

| Rows per date | Horizon | Pinned, MiB | Window filter and read-ahead of 8, MiB | Both patches, MiB | Pinned, s | Both patches, s | s per million rows, both patches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 4M | 5m | 672 | 578 | 584 | 26.1 | 24.7 | 1.23 |
| 20M | 60s | 898 | 816 | 616 | 175.1 | 123.5 | 1.24 |
| 40M | 30s | 1,038 | 934 | 597 | 463.0 | 254.6 | 1.27 |
| 80M | 15s | 1,064 | 945 | 617 | 1,402.8 | 515.0 | 1.29 |

The peak stays within 584–617 MiB across a twentyfold range of density, and time stays between 1.23 and 1.29 s per million rows. Fitted time per million rows is 1.229 + 0.0008 n, a slope 40 times smaller than before. Across the five-minute runs in 7.3, every fitted coefficient matches the published code's to within 4.4 × 10⁻¹⁶, and test R² to within 1.1 × 10⁻¹⁶.

`_iter_windows` receives only a plain `scan_parquet` or an in-memory frame, so `slice` is always cheap there. A filtered scan would not have that property, and the multi-stream path in 7.7 builds one.

### 7.5 What remains with both patches

**Look-ahead.** With the five-minute horizon, the "Both patches" column in 7.3 rises from 585 MiB at 4M to 722 MiB at 80M. From 4M upward, the fit is 541 bytes per row of look-ahead (R² 0.91), and the intercept is 592 MiB. This is a declared term of the budget, and it is now the only one that grows with rows per date.

**Threads.**

**Polars threads with both patches: 20M rows over five dates**

| POLARS_MAX_THREADS | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 1 | 476 | 16.6 | 0.6 |
| 2 | 375 | 16.1 | 0.3 |
| 4 | 441 | 17.0 | 0.1 |
| 8 | 477 | 21.1 | -0.1 |
| 12 | 516 | 24.9 | 0.1 |
| 20 (default) | 585 | 24.1 | -1.6 |

Polars sizes its buffers from the thread count: the log shows `prefetch_kbytes_limit` of 65,536 KiB at 1 or 2 threads, 131,072 at 4, 262,144 at 8, 393,216 at 12, and 655,360 at 20, which is max(64 MiB, 32 MiB × threads), and `num_pipelines` equal to the thread count. On this job, fewer threads are also faster, and `POLARS_MAX_THREADS=2` gives both the lowest peak and the shortest time. We did not trace why; oversubscription is the obvious candidate, with two workers each running queries on 20 threads while NumPy uses its own. This is one job on one machine, not a general recommendation, and a CPU-heavy feature expression may want more threads.

**One change at a time with both patches: five dates**

| Change | Peak at 4M, MiB | Time at 4M, s | Peak at 20M, MiB | Time at 20M, s |
| --- | ---: | ---: | ---: | ---: |
| Nothing | 585 | 24.1 | 625 | 134.7 |
| No model: batches are pulled and dropped | 579 | 24.9 | 599 | 133.1 |
| Allocator returns freed memory at once | 351 | 30.5 | 479 | 160.1 |
| 4 threads and immediate return | 273 | 21.6 | 285 | 117.1 |

**The prefetch budget binds when the consumer is slow.** With a fast consumer, the budget table in section 6 is flat, which by itself could mean that the budget does nothing. A consumer that holds each training batch for 300 ms lets the queue fill:

**A slow consumer: 300 ms per training batch, no model, 20M rows over five dates**

| Budget, MiB | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 16 | 615 | 125.1 | 1.5 |
| 64 | 769 | 125.4 | 1.3 |
| 256 | 1,199 | 125.4 | 1.8 |
| 1,024 | 2,019 | 125.5 | 2.0 |

**A slow consumer with both patches: 300 ms per training batch, no model, 20M rows over five dates**

| Budget, MiB | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 16 | 554 | 123.5 | 1.5 |
| 64 | 677 | 124.6 | 0.9 |
| 256 | 1,143 | 122.1 | 0.6 |
| 1,024 | 1,962 | 123.6 | 1.6 |

So the budget is a real control, but it undercounts. With both patches, the peak rises by 1.4 MiB for each MiB of budget from 16 MiB to 1,024 MiB, and by 2.5 from 16 MiB to 256 MiB. We did not trace this. A likely reason is that a batch is a slice of its window, so the window's buffers stay alive for as long as any slice does, and the budget charges only for the slice.

**The limit at high density.**

**80M rows per date under the 1 GiB limit: five dates, a five-minute horizon**

| Loader | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| patched | 690 | 621 | 67 | 643.8 | -16.3 |

Both runs are the five-minute job at 80M rows per date under the 1 GiB limit, the size at which section 6's curve is above it. With both patches the job finished, at 690 MiB. The published code was killed after 220 s of a job that takes it 1,508 s, with 26.2M rows loaded. A killed run leaves no record, so the evidence is its trace, `rss/limit80_pinned.csv`, its exit status of 247 in `followup.log`, and the kernel log:

```text
Memory cgroup out of memory: Killed process 181141 (python) total-vm:11331132kB, anon-rss:1034600kB, file-rss:67412kB, shmem-rss:4kB, UID:1000
```

### 7.6 Two questions settled along the way

**Cold and warm files.** Section 6 shows cold files costing about 150 MiB more than warm ones. Polars skips the read-ahead for row groups already in the page cache, which its log reports as `Deferred cached reads: 33 / 33 row groups`. Turning that off with `POLARS_FILE_DEFER_CACHED_READS=0` makes a warm run behave like a cold one:

**Warm files with and without deferred reads: 20M rows over five dates**

| Files | Deferred reads | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: |
| Cold | on | 672 | 26.1 | 0.4 |
| Warm | on | 540 | 24.9 | -0.3 |
| Warm | off | 712 | 25.5 | -1.2 |

**Boosting under 2 GiB.** The limit sits between the two modes' peaks at 40M rows. In-core boosting was killed and external memory finished:

**Gradient boosting that finished under the 2 GiB limit: 40M rows**

| Mode | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| external | 1,823 | 1,675 | 170 | 358.6 | 2.0 |

```text
Memory cgroup out of memory: Killed process 161649 (python) total-vm:23026236kB, anon-rss:2072028kB, file-rss:134844kB, shmem-rss:8196kB, UID:1000
```

### 7.7 Not measured

- **The multi-stream path.** `gardenpipe/data.py:1660` holds a query open in the same way and `gardenpipe/data.py:1678` writes the same kind of bound. Neither path ran in these experiments, so whether they cost the same is an inference from the code. `_open` also wraps the scan in a filter when `sources` is set, so the `slice` in `time-chunks.patch` would not carry over unchanged.
- **Why a computed column is buffered and a bare one is not.** We measured the difference and did not read the Polars source. `_RJEM_MALLOC_CONF`, `POLARS_ROW_GROUP_PREFETCH_SIZE`, and `POLARS_FILE_DEFER_CACHED_READS` are internals of Polars 2.1, and they can change.
- **Files with different row groups.** Every file here has Polars' default row groups of about 122,880 rows. Other sizes change what one slice or one window reads.

## 8. Memory results with both patches

These are the numbers the note quotes. `run_experiments.sh` and `run_weather.sh` ran again, unchanged, from a checkout with both patches (`loader_sha` `be906867b2f2`), in a directory of their own that shares the generated data through symbolic links. All 54 records finished without a traceback. Everything else on the machine used at most 0.04 of a core on average during any run. Raw outputs are in `results/patched/`.

**Number of dates: 4M rows per date, 100,000-row batches, 64 MiB budget, two workers**

| Rows | Dates | Disk, MiB | Streamed peak, MiB | Materialized peak, MiB | Streamed, s | Materialized, s | Time ratio | R² gap | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20M | 5 | 205 | 590 | 1,586 | 24.9 | 18.4 | 1.36 | 1.1e-16 | -2.0 / -0.3 |
| 40M | 10 | 409 | 609 | 2,480 | 47.4 | 36.8 | 1.29 | 4.4e-16 | -2.2 / -0.6 |
| 80M | 20 | 818 | 604 | 4,188 | 97.2 | 73.8 | 1.32 | 3.3e-16 | -4.6 / 0.4 |
| 120M | 30 | 1,228 | 622 | 6,115 | 147.6 | 106.7 | 1.38 | 4.4e-16 | -6.1 / 0.2 |
| 240M | 60 | 2,455 | 623 | 11,949 | 298.7 | 216.7 | 1.38 | 1.1e-16 | -14.4 / -3.6 |
| 360M | 90 | 3,683 | 619 | 16,890 | 440.0 | 331.2 | 1.33 | 1.1e-15 | -22.3 / 0.0 |

Materialized fit: 45.6 MiB per million rows (4.45 GiB per 100M), intercept 666 MiB, 45.2 GiB at one billion rows.

**The same 30-day streamed job, repeated**

| Run | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| scale | 622 | 147.6 | -6.1 |
| repeat | 604 | 147.7 | -8.2 |
| repeat | 607 | 149.1 | -7.0 |
| repeat | 613 | 150.8 | -5.6 |
| cap | 586 | 148.4 | -6.7 |

**Batch size: 40M rows, two workers**

| Batch rows | Budget, MiB | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: |
| 25,000 | 64 | 453 | 119.7 | 4.1 |
| 50,000 | 64 | 509 | 78.7 | -4.6 |
| 100,000 | 64 | 592 | 46.7 | -2.6 |
| 200,000 | 69 | 671 | 35.3 | -1.2 |
| 400,000 | 137 | 863 | 27.7 | -0.2 |
| 800,000 | 275 | 1,148 | 24.9 | 0.2 |
| 1,600,000 | 549 | 1,619 | 23.5 | -0.0 |

Spread of test R² across batch sizes: 8.9e-16.

**Prefetch budget: 40M rows, 100,000-row batches, two workers**

| Budget, MiB | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 16 | 557 | 58.1 | -0.3 |
| 32 | 591 | 49.6 | -2.0 |
| 64 | 600 | 48.9 | -1.8 |
| 128 | 611 | 48.5 | -2.6 |
| 256 | 620 | 44.3 | -2.0 |
| 512 | 599 | 49.4 | -3.1 |
| 1,024 | 601 | 51.4 | -2.3 |

**Workers: 40M rows, 100,000-row batches, 64 MiB budget**

| Workers | Peak, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: |
| 1 | 557 | 59.5 | -2.8 |
| 2 | 615 | 48.6 | -2.1 |
| 4 | 718 | 47.3 | -2.4 |
| 8 | 825 | 45.4 | -3.0 |

**Rows per date: ten dates, 100,000-row batches, 64 MiB budget, two workers**

| Rows per date | File, MiB | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 10 | 516 | 451 | 66 | 12.5 | -0.2 |
| 2M | 20 | 613 | 548 | 67 | 25.8 | -1.4 |
| 4M | 41 | 602 | 528 | 67 | 51.3 | -2.5 |
| 6M | 61 | 616 | 543 | 67 | 76.6 | -2.0 |
| 8M | 85 | 676 | 599 | 67 | 101.7 | -3.3 |
| 10M | 100 | 607 | 539 | 67 | 126.8 | -4.0 |
| 12M | 119 | 629 | 551 | 67 | 153.6 | -7.6 |
| 16M | 166 | 631 | 566 | 67 | 206.8 | -8.9 |
| 20M | 194 | 636 | 555 | 67 | 264.5 | -8.8 |

**Page cache: the same 40M-row job, files evicted or read first**

| Files | Runs | Lowest peak, MiB | Highest peak, MiB | Mean time, s | Most other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| cold | 3 | 591 | 600 | 50.5 | -2.3 |
| warm | 3 | 447 | 458 | 45.9 | -0.6 |

**Completed under the 1 GiB limit**

| Run | Rows | Disk, GiB | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cap | 120M | 1.20 | 586 | 516 | 67 | 148.4 | -6.7 |
| billion | 1,000M | 9.76 | 701 | 619 | 67 | 1,280.9 | -58.8 |

**Gradient boosting on the generated data: 4M rows per date**

| Mode | Rows | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Test R² | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| external | 40M | 1,848 | 1,675 | 171 | 325.1 | 0.501307 | 0.9 |
| in-core | 40M | 2,347 | – | – | 217.9 | 0.501307 | -0.3 |
| external | 120M | 4,834 | 4,661 | 171 | 890.2 | 0.496898 | 0.7 |
| in-core | 120M | 5,828 | – | – | 643.2 | 0.496898 | -0.5 |

**Against section 6.**

| Measure | Published code | Both patches |
| --- | ---: | ---: |
| Streamed peak, 5 to 90 dates, MiB | 670–730 | 590–623 |
| The 30-date job, five runs, MiB | 703–732 | 586–622 |
| Ten dates, 1M to 20M rows per date, MiB | 562–958 | 516–676 |
| Workers, 1 to 8, MiB | 580–1,125 | 557–825 |
| Cold files, 40M rows, MiB | 680–697 | 591–600 |
| Warm files, 40M rows, MiB | 524–536 | 447–458 |
| One billion rows, peak, MiB | 813 | 701 |
| One billion rows, time, s | 1,580 | 1,281 |
| Streamed time against materialized | 1.51–1.58 | 1.29–1.38 |

Test R² agrees to within 1.1 × 10⁻¹⁶ across all 48 settings that the two grids share, and exactly in most of them.

**Time at equal conditions.** Sections 6 and 8 ran hours apart, so their timings should not be subtracted: materialized runs look 6–9% slower here, and that alone could be drift. `rotation` therefore runs the same 40M-row job from each checkout in turn, changing the order each round. There were two rotations of three rounds each, the first over the published code, the filter, and both patches, and the second over the filter, both patches, and the variant described next.

**The same job from each checkout in rotation: 40M rows, ten dates**

| Mode | Loader | Runs | Mean time, s | Fastest and slowest, s | Lowest and highest peak, MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| materialize | Published | 3 | 33.3 | 33.0, 33.6 | 2,480, 2,567 |
| materialize | Window filter | 6 | 30.7 | 29.6, 31.4 | 2,431, 2,548 |
| materialize | Both patches | 6 | 35.5 | 34.8, 37.0 | 2,440, 2,541 |
| materialize | Both, a million times per query | 3 | 31.8 | 31.0, 32.3 | 2,464, 2,518 |
| stream | Published | 3 | 50.4 | 49.2, 51.2 | 688, 701 |
| stream | Window filter | 6 | 44.9 | 43.6, 45.9 | 630, 651 |
| stream | Both patches | 6 | 48.3 | 45.2, 50.1 | 595, 616 |
| stream | Both, a million times per query | 3 | 42.4 | 41.2, 43.4 | 670, 692 |

The slowdown is real, and `time-chunks.patch` causes it. The window filter alone saves 8% materialized and 11% streamed. The chunk queries then add 4.9 s materialized and 3.4 s streamed, over both rotations, though the streamed cost moved from 5.3 s in the first rotation to 1.6 s in the second. Together, the patches cost 7% materialized and save 4% streamed at this density. Test R² is the same to every printed digit across all runs of a mode.

`chunk_query.py` times one chunk with a fresh scan, as the patch does: 3–8 ms on the 4M file and 3–11 ms on the 80M file, at 20 threads, and 1–2 ms on one thread. Swapping `select` and `slice` changes nothing, because the optimized plans are identical. We did not separate the cost of the queries from the cost of decoding, which the open query used to do ahead of the consumer.

**More times per query, tested and not adopted.** `larger-time-chunks.patch` fetches a million times per query instead of one batch of them, so ten times fewer queries at the default batch size. `_time_windows` takes chunks of any size, and GardenPipe's 190 tests pass. It wins the time back, and it costs far more memory than the 8 MiB that a million times occupy:

**A million times per query at 80M rows per date: five dates**

| Horizon | Look-ahead rows | Both patches, MiB | A million times per query, MiB | Both patches, s | A million times per query, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 15s | 13,888 | 617 | 752 | 515.0 | 434.5 |
| 5m | 277,777 | 722 | 829 | 631.1 | 588.4 |

With the look-ahead at 13,888 rows, the peak at 4M rows per date is 670–692 MiB in the rotation, against 595–616 MiB without it. Test R² is unchanged. So this is a trade and not a fix: 7–16% less time for 13–22% more memory. The note is about memory, so its tables keep the two patches. We did not try sizes between one batch and a million rows. Section 13.5 later showed that raising `batch_size` gets more of the time back for about the same memory, so ridge does not need this patch at all.

**The bump at 8M rows per date.** In the rows-per-date table, 8M stands out at 676 MiB between 616 MiB at 6M and 607 MiB at 10M. The published code has a smaller bump at the same place, and the 8M file is about 5% larger per row than its neighbours. Three more runs at each of the three sizes:

**Ten dates repeated with both patches: three runs at each size**

| Rows per date | Peak of each run, MiB | Spread, MiB | Mean time, s |
| --- | ---: | ---: | ---: |
| 6M | 618, 606, 625 | 18 | 76.4 |
| 8M | 603, 647, 692 | 90 | 101.7 |
| 10M | 619, 599, 612 | 20 | 128.7 |

So 8M is not a fixed bump, but it is not ordinary noise either. With the grid's run, four runs at 8M span 603–692 MiB, while four at 6M span 606–625 MiB and four at 10M span 599–619 MiB. The same job on the same data can peak 89 MiB apart, and we did not trace why. Peak RSS is the height of one spike, so read any single peak in these tables as good to a few tens of MiB.

**The billion-row job.** It peaked at 701 MiB in 1,281 s, and at 695 MiB in 1,306 s when run again:

**The billion-row job repeated with both patches, under the 1 GiB limit**

| Rows | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1,000M | 695 | 628 | 67 | 1,306.5 | -45.0 |

That is about 90 MiB above ten dates at the same density, which the repeats above put at 599–619 MiB. The excess is not noise, and it does not accumulate. Cut into twenty equal stretches, both traces, `rss/billion.csv` and `rss/chunk_billion.csv`, are high in the same two parts of the run, about 25–45% and 60–85% of the way through, and both end near 600 MiB:

| Trace | Peak of each twentieth of the run, MiB |
| --- | --- |
| First run | 569, 582, 545, 576, 589, 624, 642, 623, 626, 610, 596, 618, 671, 686, 680, 682, 672, 628, 597, 598 |
| Second run | 571, 594, 547, 597, 577, 673, 669, 678, 656, 553, 578, 560, 672, 694, 685, 671, 673, 568, 596, 576 |

We did not trace which phase of the job holds the extra memory.

**The materialized run under the limit.** The 30-date job was killed about 22 s in. Until 21.0 s it never passed 550 MiB, while the streamed run reached 563 MiB in the same time. Then it went from 550 MiB to 1,074 MiB in 0.4 s. The kernel log records the cause:

```text
Memory cgroup out of memory: Killed process 200789 (python) total-vm:10162864kB, anon-rss:1037948kB, file-rss:65620kB, shmem-rss:4kB, UID:1000
```

**Boosting under the limits.** The patches do not touch XGBoost's memory: the peaks above are within 0.2% of section 6. Under 1 GiB on 40M rows both modes were killed, in-core after about 45 s and external memory after about 38 s. Under 2 GiB the in-core run was killed and external memory finished:

**Gradient boosting that finished under the 2 GiB limit with both patches: 40M rows**

| Mode | Peak RSS, MiB | Peak anonymous, MiB | Peak file-backed, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| external | 1,853 | 1,682 | 171 | 289.1 | 7.1 |

```text
Memory cgroup out of memory: Killed process 213533 (python) total-vm:22538608kB, anon-rss:2072384kB, file-rss:169732kB, shmem-rss:8196kB, UID:1000
```

From 40M to 120M rows, peak RSS grows by about 46 bytes per row in core and 39 with external memory. So external memory saves 17–21% of the peak at 1.4–1.5 times the time.

## 9. Weather results

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

**With both patches.** `run_weather.sh` ran again from the patched checkout, and the forecasts did not move. `predictions.parquet`, `metrics.json`, and `validation.json` are identical to the published code's, every value exactly equal, and so are all the error tables above. Only time and memory change, and these are the figures the note quotes:

**Ridge on random Fourier features, weather data**

| Random features | Seed | Inputs | X′X, MiB | α | Test MAE, °C | Test RMSE, °C | Peak RSS, MiB | Time, s | Other CPU, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0 | 18 | 0.00247 | 0.1 | 1.7045 | 2.2096 | 250 | 9.1 | -0.6 |
| 500 | 0 | 518 | 2.05 | 1.0 | 1.4197 | 1.8667 | 304 | 14.3 | -0.1 |
| 2,000 | 0 | 2,018 | 31.1 | 1.0 | 1.3596 | 1.7938 | 461 | 26.4 | 0.2 |
| 2,000 | 1 | 2,018 | 31.1 | 1.0 | 1.3665 | 1.8020 | 457 | 27.9 | -0.0 |
| 2,000 | 2 | 2,018 | 31.1 | 1.0 | 1.3510 | 1.7863 | 460 | 27.1 | -0.2 |
| 2,000 | 3 | 2,018 | 31.1 | 1.0 | 1.3589 | 1.7980 | 452 | 28.5 | 0.0 |
| 4,000 | 0 | 4,018 | 123 | 1.0 | 1.3464 | 1.7836 | 1,063 | 61.9 | 1.1 |

| Batch rows | Published: time, s | Published: peak, MiB | Both patches: time, s | Both patches: peak, MiB |
| --- | ---: | ---: | ---: | ---: |
| 5,000 | 45.3 | 316 | 40.1 | 241 |
| 20,000 | 17.1 | 302 | 18.2 | 250 |
| 1,000,000 | 10.9 | 295 | 10.0 | 237 |

Gradient boosting took 18.7 s and peaked at 493 MiB with both patches.

## 10. Corrections

### 10.1 The first pass

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

The same test gave 478 and 561 MiB, warm and cold, at 1M rows per date, and 626 and 806 MiB at 10M. So the sampler has no effect, and the extra memory is real, because it is anonymous. The first pass's 535 MiB was therefore a best case, seen because its files were freshly written and still cached. Section 7.6 traces the difference to Polars' read-ahead. Every run now starts cold.

**Other jobs ran during the timed runs.** From 16:24 to 16:56 CET, the weather model comparisons ran alongside the data-size grid, so those timings are too long and the time ratio is unreliable. The 30-date job took 177 s streamed and 124 s materialized in that grid, against 153 s and 95 s when run alone. The same applies to the first-pass times for random features, for weather boosting, and for `train.py` at batch sizes of 5,000 and 1,000,000. Peaks were not visibly affected: the 30-date materialized run peaked at 6,040 MiB in the grid and 6,043 MiB alone. Every record now carries `other_cpu_seconds`.

**Boosting did not run with the settings reported.** The search space contained `num_boost_round`, but that is a setting of `XGBoostAdapter`, not an XGBoost parameter. XGBoost ignored it with a warning, `Parameters: { "num_boost_round" } are not used`, and every fit used the adapter's default of 100 rounds. The model described as "800 rounds" had 100 trees, which `num_boosted_rounds()` confirmed. Its depth had also been chosen at the edge of the grid. `compare_models.py` now picks the number of rounds by early stopping on the validation folds, over a wider grid, and the refit uses the median round of the selected trial. The effect was modest, because early stopping lands near the old count at these settings, but one conclusion changed: random features come within 1–2% of boosting rather than matching it.

| Boosting | Trees | Test MAE, °C | Test RMSE, °C | MAE reduction from ridge, 95% interval |
| --- | ---: | ---: | ---: | ---: |
| First pass: depth 7, η = 0.05 | 100 | 1.3586 | 1.7970 | 20.3%, 18.6–21.9% |
| Final: depth 9, η = 0.02 | 272 | 1.3329 | 1.7695 | 21.8%, 20.1–23.4% |

**Early traces measured the wrong process.** The first grid launched `uv run python`, so the sampler read the `uv` wrapper, at about 42 MiB, instead of Python. Those traces were discarded and are not in `results/first-pass/`. Peak RSS from `ru_maxrss` was read inside Python and is unaffected. The scripts now call `.venv/bin/python` directly.

**External memory was judged by RSS alone.** Peak RSS with XGBoost's external memory rose from 1.8 GiB to 4.8 GiB when the data tripled, but RSS includes mapped cache pages that the kernel can drop. `sample_rss.py` now splits RSS into anonymous and file-backed pages, so the two can be told apart. The split shows that the growth is anonymous, not mapped cache: see section 6.

**Smaller errors.** The draft described a "20-core machine"; it has 12 cores and 20 threads. A figure label gave *X′X* for 18 features as 2.6 KiB; 18² × 8 bytes is 2.5 KiB.

### 10.2 Wrong turns in the follow-ups

Section 7 gives the conclusions. These are the steps on the way that were wrong, some of which were reported as findings at the time.

- **"No quadratic reread."** An early probe found that a window reads 3 of 163 row groups, and that was taken as proof that windows do not rescan the file. The probe filtered on `pl.col("time")`, and GardenPipe filters on `_epoch_ns(time)`. With the real expression, the same window reads 162 of 163. The probe answered a different question from the one asked.
- **Look-ahead as the cause.** It was the leading hypothesis for the rise with rows per date. Holding look-ahead fixed left the rise in place (7.2).
- **The window filter as the cause of the memory rise.** It explained the time so neatly that it was reported as the likely cause of both. The curve measured with the patch showed no drop in the peak (7.3).
- **"Fills once, then drains."** The first reading of the traces was a read-ahead buffer filling at the start of a date. The steps actually follow the number of open dates: two in training and one in validation and test (7.4).
- **Allocator decay as the slope.** A sharp account in which allocator retention explained both the rise and an apparent flattening near 950 MiB did not survive. It removes about 250 MiB at both sizes tried. The flattening between 16M and 20M in section 6 is the rise in 7.1 slowing down, and run-to-run spread.
- **The second Polars probe.** It selected the bare column and a fast consumer, and it reported the read-ahead limit as a complete fix. With GardenPipe's expression, at the pipeline's pace, about 200 MiB remains (7.4). This was the same mistake as the first item. Both times the probe differed from the real query in a detail that seemed not to matter.
- **The materialized slowdown as a missing pushdown.** Materialized runs took 6–9% longer with both patches, and this was first blamed on `.select()` coming before `.slice()` in `_time_chunks`, on the theory that an in-memory frame would compute the whole column for every chunk. Both halves were wrong. Materialized training reads Parquet through `_iter_windows`, as streamed training does, and only validation and test call `materialize()`, so no in-memory frame was involved. And Polars pushes the slice down in either order: `chunk_query.py` prints identical optimized plans on Parquet, and in memory, with a `ms` or `us` column that the expression has to convert, one chunk takes 0.1–0.5 ms at 4M and 80M rows, against about 4 ms and 71 ms for the whole column. Swapping the two calls therefore changes nothing. A rotation of the checkouts then showed that the slowdown is real and comes from `time-chunks.patch` (section 8), so the first explanation was wrong and the observation was right.
- **A 30-day gain that was too good.** On Polars 2.0.0, the published 30-day run read 673 MiB against 450 MiB patched. It had probably lost part of the page cache to other programs, and four runs in rotation gave 526–528 MiB against 435–452 MiB (section 13.2). The first figure was never reported as a result.
- **"3,683 of 3,683 MiB resident."** `page_cache.py warm` printed that just before a run that started with 39 of its 409 MiB resident. It measured each file right after reading it, and with ComfyUI holding about 21 GiB, the later files pushed out the earlier ones. `page_resident.py` showed the gap, those runs were left out (13.2), and `page_cache.py` now measures once everything has been read.
- **The third patch as the only fix.** `larger-time-chunks.patch` was first offered as the only tested way to win the time back, while the batch-size table in section 8 already showed a better trade. A question about whether batch size is adjustable exposed that, and section 13.5 measured it.
- **Proportions read off a small run.** The steps of a materialized split were first reported from 1M-row splits on four threads, as up to 245 bytes per row with `ctx` close to a quarter, on the assumption that the proportions would hold. They do not: see section 13.4. The full-size run also found what the small one had hidden, the previous split's `ctx` still alive. Its size was first put at 572 MiB, an arithmetic slip for 509 MiB, so the match with the measured 575–590 MiB was weaker than it looked. The weak references settled it, not the sizes.
- **"The same cost in both modes."** The first rotation showed the chunk queries adding 5.6 s materialized and 5.3 s streamed, and that match was reported as proof of a fixed cost per chunk. The second rotation gave 4.1 s and 1.6 s. The cost is real, but that argument for its cause did not survive a repeat.
- **"About 8 MiB per open date."** Fetching a million times per query was proposed at that price, the size of the times themselves. It costs 80–135 MiB, because what the query uses on the way is what counts. The same oversight, one level down: the size of the data was taken for the size of the work.

## 11. What should match

| Quantity | What to expect on your machine |
| --- | --- |
| Generated files | Identical bytes with the pinned versions: compare the SHA-256 lines in `experiments.log` |
| Forecasts and test scores | The same to within rounding with the pinned versions, whichever machine you use. BLAS and thread count can move the last few digits |
| Streamed against materialized R² | Agree to about 10⁻¹⁵ |
| Peak RSS, shape | Flat in the number of dates, rising with batch size and workers. With the published code it also rises with rows per date. With both patches it stays flat in rows per date at a fixed look-ahead in rows |
| Peak RSS, size | Depends on thread count and allocator: Polars sizes its pools from the number of threads, so expect different constants on a different CPU count |
| Time | Depends on the machine. Ratios travel better than seconds. With the published code, time per row grows with rows per date; with the window filter it does not, at a fixed look-ahead in rows |
| Under the 1 GiB limit | Streamed finishes and materialized is killed, as long as the streamed peak on your machine stays below the limit |

## 12. Files

| Path | Contents |
| --- | --- |
| `results/uv.lock` | Exact package versions, to copy into the GardenPipe checkout |
| `results/environment.txt` | Machine, kernel settings, and full package list for the clean run |
| `window-filter.patch`, `time-chunks.patch` | The two changes to `gardenpipe/data.py`, to apply in that order |
| `larger-time-chunks.patch` | A third change, tested and not adopted: see section 8 |
| `chunk_query.py` | What one chunk of times costs, and the plans for both orders of `select` and `slice` |
| `time-column-guard.patch` | The guard for unusual time columns, in GardenPipe as `89d7244`: see section 13 |
| `apply_check.sh`, `compare_apply_check.py`, `page_resident.py` | The same jobs before and after the patches, their comparison, and what is in the page cache |
| `loader_column_types.py`, `compare_column_types.py`, `window_filter_types.py` | The loader and the window filter on other kinds of time column |
| `materialize_steps.py` | Memory at each step of a materialized split |
| `multi_source_check.py` | Every batch of instruments and sources, published against patched |
| `results/results.jsonl` | One line per memory run on the published code, with every setting and result |
| `results/results_followup.jsonl` | One line per run behind section 7 |
| `results/contaminated.jsonl` | The runs rejected because the machine was busy |
| `results/superseded.jsonl` | The first `fix-curve` runs, made with the shorter form of the window filter |
| `results/followup.log` | Complete output of `run_followups.sh`, with timestamps |
| `results/patched/` | The full grids with both patches, in the same layout, behind section 8, with the weather CSV files the figures read |
| `results/apply_check/` | The raw output of section 13 |
| `results/rff.jsonl`, `results/boosting_weather.jsonl` | Time, memory, and error by model on the weather data |
| `results/weather.log`, `results/experiments.log` | Complete output of the two run scripts on the published code, with timestamps |
| `results/failfast.log` | The rejected budget and its message |
| `results/cache-test/` | The warm and cold comparison that found the page-cache effect |
| `results/rss/` | RSS traces, as `t,rss_mib,anon_mib,file_mib` |
| `results/first-pass/` | The superseded first pass, kept for section 10 |

## 13. Applying the patches

On 2026-11-06 both patches went into the GardenPipe working copy, in order, with `git apply`. `gardenpipe/data.py` went from `7c64551632de` through `3eb3b1aaf173` to `be906867b2f2`, byte for byte the file behind section 8.

They were then committed one at a time, with the guard of 13.3 after them, and `main` was fast-forwarded to the result.

| Commit | Holds | `gardenpipe/data.py` |
| --- | --- | --- |
| `4066ad2cca4a6d735014baabfa3c5ec01bdf53cc` | The window filter | `3eb3b1aaf173` |
| `ab41d3846e20acd4dd1136b6c03a832b0c051dfe` | The time chunks and the new table in GardenPipe's README | `be906867b2f2` |
| `89d72445201635a99b3ee373ba4782bababf7cf0` | The guard | `d2baba8ea452` |

So a checkout of `ab41d38` has the same `data.py` as applying both patches, and `89d7244` the same as applying all three.

The grids ran on Polars 2.1.0. The repository's own `.venv` has 2.0.0, which its README's table also names, and `pyproject.toml` allows 1.41.2 and later. The window filter also stopped going through `_epoch_ns`, and the grids only ever used one kind of time column. So the change was checked on those versions and on other kinds of time column. The raw output is in `results/apply_check/`.

### 13.1 Tests

Two test files import torch, which none of these environments has, so they were left out. The five failures are all in `tests/test_viewer.py`, on unpatched code too: that `.venv` has no plotly.

| Polars | Published | Both patches |
| ---: | --- | --- |
| 1.41.2 | 190 passed | 190 passed |
| 2.0.0 | 173 passed, 12 skipped, 5 failed | 173 passed, 12 skipped, 5 failed |
| 2.1.0 | 190 passed | 190 passed |

The commits themselves were tested as well, unpacked with `git archive`: `4066ad2` on 2.0.0, and `ab41d38` and `89d7244` on 2.0.0 and 1.41.2. The counts are the same as in the table.

### 13.2 The same jobs on Polars 2.0.0

The jobs ran before and after the patches on that `.venv`. `examples/minimal.py` is the job behind the table in GardenPipe's README.

| Job | Published | Both patches |
| --- | ---: | ---: |
| `minimal.py`, 10 days, data in the page cache | 550 MiB, 51.3 s | 440 MiB, 48.9 s |
| `minimal.py`, 30 days, data in the page cache | 526, 528 MiB; 152.4, 154.3 s | 435, 452 MiB; 142.0, 144.4 s |
| `minimal.py`, 10 days, cold | 685 MiB, 53.0 s | 615 MiB, 49.9 s |
| 20M rows per date, 60 s horizon, five dates | 910 MiB, 176.3 s | 601 MiB, 124.9 s |
| 40M rows per date, 30 s horizon, five dates | 1,030 MiB, 469.9 s | 641 MiB, 257.5 s |
| Weather, batches of 5,000 rows | 258 MiB, 43.0 s | 252 MiB, 47.0 s |
| Weather, batches of 20,000 rows | 261 MiB, 18.4 s | 261 MiB, 19.8 s |
| Weather, batches of 1,000,000 rows | 258 MiB, 9.4 s | 264 MiB, 8.2 s |

The results did not move. The `minimal.py` scores are the same to their printed digits. On the two fixed look-ahead jobs, the R² gap is zero, coefficients differ by at most 2.2e-16, and intercepts by at most 6.9e-18. All 17,377 weather predictions are exactly equal at each batch size, and `validation.json` is byte-identical.

Polars 2.0.0 shows what 2.1.0 showed. The grids have 898 and 1,038 MiB published, in 175.1 and 463.0 s, and 616 and 597 MiB with both patches, in 123.5 and 254.6 s.

GardenPipe's README gave about 530 MiB at 10 and 30 days. Published runs reproduce that with the data in the page cache, and both patches lower it to 435–452 MiB, so since `ab41d38` the table says about 440 MiB and names the page cache. The weather table in GardenPipe does not move with the patches, though its 308–346 MiB were already above the 258–261 MiB measured here on published code.

Other programs used up to five CPUs during these runs, so apart from the 30-day row, which ran in rotation, a few seconds' difference means nothing. The weather times are not comparable with section 9.

**A disturbed run.** The first published 30-day run in `before/` read 673 MiB and 167.2 s, and the patched run in `after/` read 450 MiB and 147.2 s. That gap was too large to be real: the note's own warm runs of the published code stayed near 530 MiB, and available memory had fallen to 7,115 MiB around that time, so part of the data had probably left the page cache. Residency was not being read then, so that cause is an inference. The table's 30-day row comes from `apply_check.sh rotate` instead: published, patched, patched, published, with all 1,228 MiB of the data resident before and after every run.

**Polars 1.41 on the README's job.** The README also said that Polars 1.41 needs about 40 MiB less. That figure came from the published code, so `apply_check.sh versions` ran the patched job on both versions in turn. ComfyUI was holding about 21 GiB of memory throughout, and the load average reached 25, so only the peak is read from these runs, not the time.

| Days | Polars 2.0.0 | Polars 1.41.2 |
| ---: | ---: | ---: |
| 10 | 426 MiB, and 440 MiB in the table above | 420, 400 MiB |
| 30 | 447 MiB, and 435, 452 MiB in the table above | 402, 403 MiB |

The gap is about 23 MiB at 10 days and 42 MiB at 30, so the README now says about 30 MiB.

The first pair of runs in `versions.log` is left out. They ran on Polars 2.0.0 and started with 39 of 409 and 614 of 1,228 MiB resident, and they read 613 and 605 MiB, close to the cold run's 615 MiB. In the runs kept, the 10-day data stayed fully resident, and the 30-day runs started with 1,212–1,223 of 1,228 MiB resident and ended with all of it.

### 13.3 Other kinds of time column

`loader_column_types.py` runs the real `FeatureLoader` on 17 kinds of column, each with two horizons, from a file and from a frame, on both engines. That is 136 cases per Polars version, each compared by a digest of every batch.

| Time column | Polars 1.41.2 | Polars 2.0.0 and 2.1.0 |
| --- | --- | --- |
| `Datetime` in ns, us, or ms, naive or with a time zone | Identical | Identical |
| `Date`, `Int64`, `UInt64`, `Float64` | Identical | Identical |
| `Int32`, `UInt32`, when end plus horizon overflows the type | **Newly raises** | **Newly raises** |
| ISO `String` | **0 rows instead of 5,000, no error** | Both fail |
| Other `String` formats, `Time`, `Duration` | Both fail | Both fail |

Both changes come from `last.cast(dtype)` in the window filter, which puts the bound in the column's own type. A 32-bit integer read as nanoseconds spans 2 or 4 seconds, so a horizon of seconds overflows it. Polars before 2.0 casts ISO strings to datetimes, so the published filter worked on them. The patched filter compares text instead, its literal has a space where the column has a `T`, and the whole date comes back empty. Polars 2 removed that cast, so there both versions fail with the same error.

`window_filter_types.py` tests the filter alone, at more boundaries than real windows reach, on a frame and on a Parquet scan. All 7,440 cases per version on `Datetime`, `Date`, and `Int64` match, including times before 1970 and bounds that fall between two ticks of the column's unit. On `Float64`, 44 of 868 cases differ, because a double cannot hold a nanosecond epoch exactly. On `UInt64`, 120 of 672 raise, on negative bounds, which a real window never has. Neither shows up in the loader runs.

**The guard.** `time-column-guard.patch`, on top of both patches, uses the bare column only for `Datetime`, `Date`, and `Int64`, and keeps the published expression for everything else. It matched the published loader in all 136 cases on all three versions, had no differences in `window_filter_types.py`, and passed the tests of 13.1 with the same counts. It went into GardenPipe as `89d7244`, so the two regressions in the table above are gone from `main`.

For a `Datetime` column it builds the same filter as the two patches. To confirm that, the jobs of 13.2 ran again with it on Polars 2.0.0.

| Job | Both patches | With the guard |
| --- | ---: | ---: |
| `minimal.py`, 10 days, data in the page cache | 440 MiB, 48.9 s | 453 MiB, 49.1 s |
| `minimal.py`, 30 days, data in the page cache | 450 MiB, 147.2 s | 421 MiB, 150.7 s |
| `minimal.py`, 10 days, cold | 615 MiB, 49.9 s | 596 MiB, 52.0 s |
| 20M rows per date, 60 s horizon, five dates | 601 MiB, 124.9 s | 613 MiB, 139.2 s |
| 40M rows per date, 30 s horizon, five dates | 641 MiB, 257.5 s | 618 MiB, 271.2 s |
| Weather, batches of 5,000 rows | 252 MiB, 47.0 s | 263 MiB, 38.8 s |
| Weather, batches of 20,000 rows | 261 MiB, 19.8 s | 271 MiB, 13.6 s |
| Weather, batches of 1,000,000 rows | 264 MiB, 8.2 s | 270 MiB, 7.8 s |

The peaks move both ways, by up to 29 MiB, which is the scatter of these runs. The results do not move: the R² gap is zero, coefficients differ by at most 2.2e-16 and intercepts by at most 2.1e-17, and all 17,377 weather predictions are exactly equal. ComfyUI held about 20 GiB of memory during these runs, so they ran with `QUIET_FREE_MIB=4000`, and other programs were using CPU, so read the times as rough. `results/apply_check/guard/` has the output.

### 13.4 Where a materialized split's memory goes

`materialize_steps.py` reads RSS and peak at each step inside `materialize()`, on the 40M-row job: ten dates, so three splits of 8M rows, at the default 20 threads.

| Step | Bytes per row of the split |
| --- | ---: |
| `collect`: the final frame, by `estimated_size` | 34 |
| `collect`: the rest of the rise | 80–89 |
| Features and target to NumPy | 32–38 |
| Building `ctx` | 36–45 |
| **Start of the split to its peak** | **188–197** |

That is 1,427–1,498 MiB per split. The job peaks in the second validation split, which starts from 1,062 MiB where the test split starts from 472 MiB. So the three splits peak at 1,864, 2,560, and 1,899 MiB. A first run of the script gave 1,876, 2,474, and 1,879 MiB, in line with the 2,440–2,541 MiB of the rotation in section 8.

The 590 MiB head start, 78 bytes per row, is the first split's `ctx`. `gardenpipe/pipeline.py:809` binds `ctx` in the fold loop, and that name keeps it alive through the next fold's fit and load. The script holds a weak reference to each `ctx["date"]` array. One is alive when the second split starts, two once its own is built, and none by the end of `train()`.

`ctx` is that large because `.to_numpy()` on the `date` column makes one Python string per row: 1,000 distinct objects in the first 1,000 rows, 51 bytes each by `sys.getsizeof`, plus an 8-byte pointer, all holding the same date. `tag` shares one object but still takes a pointer per row. Those sizes come to 509 MiB. The rest of the 590 MiB was not traced.

Not measured: how much of the 80–89 bytes is live query data and how much the allocator kept. Not tested: dropping `ctx` sooner, or building it without one string per row. The test split shows what a clean start gives in this job, about 1,900 MiB.

The proportions depend on scale. With 1M-row splits on four threads, the same steps gave 181–197 bytes for the whole `collect`, 16 for NumPy, and 54–76 for `ctx`.

### 13.5 Batch size and the patches

Batch size moves the level of the peak and leaves the rise with rows per date where it was. The patches do the opposite. This is the fixed look-ahead job of five dates, as peak MiB:

| Rows per date | Published, 100,000-row batches | Both patches, 100,000 | Published, 200,000 | Both patches, 200,000 |
| ---: | ---: | ---: | ---: | ---: |
| 4M | 672 | 584 | 724 | 699 |
| 20M | 898 | 616 | 958 | 697 |
| 40M | 1,038 | 597 | 1,086 | 692 |

The 100,000-row columns are the grids on Polars 2.1.0, and the 200,000-row columns ran on 2.0.0. From 4M to 40M rows per date, the published peak rises by 366 and 362 MiB at the two batch sizes, while with both patches it moves by 13 and −7 MiB. At 200,000-row batches the times were 18.0, 110.3, and 279.9 s published, against 18.4, 92.1, and 184.6 s patched, with the R² gap at zero and coefficients within 2.2e-16.

Raising `batch_size` also does better than `larger-time-chunks.patch`. This is the 40M-row job on Polars 2.0.0, each setting twice, in rotation and then in reverse:

| Setting | Materialized, s | Materialized peak, MiB | Streamed, s | Streamed peak, MiB |
| --- | ---: | ---: | ---: | ---: |
| Published, 100,000-row batches | 35.2, 36.2 | 2,390, 2,441 | 51.9, 52.1 | 683, 674 |
| Both patches, 100,000 | 37.5, 39.6 | 2,369, 2,343 | 49.1, 50.8 | 602, 603 |
| Both patches, 200,000 | 30.6, 30.6 | 2,377, 2,377 | 36.3, 35.8 | 696, 701 |
| Both patches and `larger-time-chunks.patch`, 100,000 | 35.5, 34.2 | 2,365, 2,452 | 43.6, 42.4 | 678, 677 |

Test R² agrees to 13 digits across all 16 runs. A larger batch cuts the window queries as well as the timestamp queries, and the patch cuts only the timestamp queries. So against the patch, doubling `batch_size` takes 16% less time streamed and 12% less materialized, for about 20 MiB more streamed peak, and needs no code. The patch is not needed for ridge on this job. Batch size is not free for every model, though: for `TorchAdapter` it is part of the training.

The materialized slowdown of section 8 shows here too, at 8%. At 200,000-row batches the patched run beats the published run at 100,000. The published code was not run materialized at 200,000, so this shows that the slowdown can be outrun, not that it disappears. Two published runs in the first round saw 19 s and 30 s of other CPU, and their repeats agree with them to within a second.

### 13.6 Instruments and sources

The patches change how a date's times are read and how a window's rows are filtered. They do not change where windows end. Windows are still time ranges of at most `batch_size` rows, unless one timestamp has more, and `_time_windows` still cuts them, from the same sorted times.

`multi_source_check.py` compares every batch on three instruments with irregular, partly shared timestamps, about 31,000 rows on Polars 2.0.0, at two batch sizes and on both engines. It covers instruments in one file with `target_by`, and `MultiSourceLoader` on one shared file and on one file per source, in the wide and long layouts. All 20 cases are identical between published and patched, and no timestamp falls in two batches.

Instruments in one file do go through the patched code, and rows that share a timestamp stay in one window. `MultiSourceLoader` reaches neither patched function: `_filter_window` is called only from `_load_date_frame` when it has a window, and `_iter_windows` belongs to `FeatureLoader`. That also means it has neither fix: `_window_ends` reads a shared file's times through `collect_batches`, and `span` in `_window_outs` still filters through `_epoch_ns`. Measuring what that costs is in progress.

### 13.7 Reproduce

`CODE` is a checkout, `NOTE` is this folder, and `WORK` holds the data from section 2. `results/apply_check/packages-polars-*.txt` has the exact versions.

```sh
# The lower bound, in an environment of its own
uv venv "$WORK/pl141" --python 3.12
uv pip install --python "$WORK/pl141/bin/python" polars==1.41.2 cloudpickle numpy optuna tqdm pytest \
  scikit-learn xgboost plotly matplotlib anywidget ipywidgets

# Tests, from each checkout, with each Python
python -m pytest -q --ignore=tests/test_sample_weight.py --ignore=tests/test_torch_adapter_snapshots.py

# Other kinds of time column: VERSION is 1.41.2, 2.0.0, or 2.1.0, and NAME is published, patched, or guarded
PYTHONPATH=$CODE python "$NOTE/loader_column_types.py" "$WORK/tmp" > "$OUT/polars-$VERSION.$NAME.json"
python3 "$NOTE/compare_column_types.py" "$OUT"
PYTHONPATH=$CODE python "$NOTE/window_filter_types.py" "$WORK/tmp"

# The same jobs before and after, about 15 and 10 minutes, then the rotation, about 12
CODE=$PUBLISHED PY=python WORK=$WORK OUT=$OUT "$NOTE/apply_check.sh" before
CODE=$PATCHED PY=python WORK=$WORK OUT=$OUT "$NOTE/apply_check.sh" after
python "$NOTE/compare_apply_check.py" "$OUT/before" "$OUT/after"
PUBLISHED=$PUBLISHED PATCHED=$PATCHED PY=python WORK=$WORK OUT=$OUT "$NOTE/apply_check.sh" rotate

# The guard: the same jobs on a checkout with it, compared with the run above, about 12 minutes
CODE=$GUARDED PY=python WORK=$WORK OUT=$GUARD_OUT "$NOTE/apply_check.sh" after
python "$NOTE/compare_apply_check.py" "$OUT/after" "$GUARD_OUT/after"

# The README's table on two versions of Polars, about 14 minutes
PATCHED=$PATCHED PY=python OLD_PY="$WORK/pl141/bin/python" WORK=$WORK OUT=$OUT "$NOTE/apply_check.sh" versions

# Batch size and the patches, about 20 and 15 minutes. LARGER has larger-time-chunks.patch on top of both.
PUBLISHED=$PUBLISHED PATCHED=$PATCHED LARGER=$LARGER PY=python WORK=$WORK OUT=$OUT "$NOTE/apply_check.sh" batch
PUBLISHED=$PUBLISHED PATCHED=$PATCHED PY=python WORK=$WORK OUT=$OUT "$NOTE/apply_check.sh" slope
python3 "$NOTE/compare_apply_check.py" "$OUT/batch/runs.jsonl"

# Instruments and sources, in seconds
PYTHONPATH=$CODE python "$NOTE/multi_source_check.py" "$WORK/tmp" > "$OUT/$NAME.json"
python3 "$NOTE/multi_source_check.py" --compare "$OUT/published.json" "$OUT/patched.json"

# A materialized split, step by step
PYTHONPATH=$CODE python "$NOTE/materialize_steps.py" "$WORK/d4m" 10
POLARS_MAX_THREADS=4 PYTHONPATH=$CODE python "$NOTE/materialize_steps.py" "$WORK/d1m" 5
```

`apply_check.sh` is the scripts behind 13.2 and 13.5 with their paths turned into settings. In that form it was run through on tiny data, not again at these sizes. The exception is `versions`, which was written later and ran at full size as it stands here.
