# GardenPipe note: experiments

The scripts behind the note *Arbitrarily large data, bounded memory*. They run against
[GardenPipe](https://github.com/LiJ21/GardenPipe) at commit `9bc5e3e`, on Linux with Python 3.12 and Polars 2.1. The
note quotes that commit with two small changes to `gardenpipe/data.py`, kept here as `window-filter.patch` and
`time-chunks.patch`, to apply in that order. In GardenPipe they are commits `4066ad2` and `ab41d38`, and `main` has
both since `89d7244`, which adds `time-column-guard.patch` for unusual time columns. `RESULTS.md` holds the results
with and without them, and explains `larger-time-chunks.patch`, a third change that was tested and not adopted.
`multi-source-reads.patch` brings the same two fixes to `MultiSourceLoader`, and is in GardenPipe as `693cc4b`.
`multi-source-filter.patch` is its first half, for measuring that half alone.

```sh
git clone https://github.com/LiJ21/GardenPipe && cd GardenPipe && git checkout 9bc5e3e
cp "$NOTE/results/uv.lock" .
uv sync --frozen --extra viz --extra linear --extra xgboost
uv run python examples/weather/prepare.py
uv run python examples/weather/train.py
uv run python examples/weather/report.py
```

`RESULTS.md` holds the results, the exact versions, and the full recipe. In short, from that checkout, with `NOTE`
pointing here and `WORK` at a scratch directory:

| Script | Purpose |
| --- | --- |
| `record_environment.sh` | The machine and software behind a run |
| `run_weather.sh` | Every weather result, in about 15 minutes |
| `run_experiments.sh` | The full memory grid, in about 2.5 hours |
| `run_followups.sh` | Why the peak moved with rows per date, and each patch measured alone. Phases that need a patched checkout refuse to run from any other |
| `quiet.py` | Wait for an idle machine before a run, and reject a run that was disturbed |
| `summarize.py` | Print the memory results as the tables in `RESULTS.md` |
| `generate_data.py` | Write the generated dataset, in its own process |
| `page_cache.py` | Put a dataset in or out of the page cache before a run |
| `measure_memory.py`, `run_record.py` | One measured run in a fresh process, and what it records about itself |
| `reader_memory.py` | One Polars query over one file, with no GardenPipe involved |
| `chunk_query.py` | What one chunk of times costs, and whether `select` and `slice` can change places |
| `apply_check.sh`, `compare_apply_check.py`, `page_resident.py` | The same jobs before and after the patches, on Polars 2.0.0 |
| `loader_column_types.py`, `compare_column_types.py`, `window_filter_types.py` | The loader and the window filter on other kinds of time column |
| `materialize_steps.py` | Memory at each step of a materialized split |
| `multi_source_check.py` | Every batch of instruments and sources, published against patched |
| `panel_data.py`, `measure_panel.py`, `panel_steps.py` | `MultiSourceLoader`: three stations from the generated data, one measured run, and memory at each step of one date |
| `multi_source_types.py`, `multi_source_units.py` | `MultiSourceLoader` on each kind of time column, and with a different time unit on each stream, batch by batch, to compare two checkouts |
| `measure_boosting.py`, `boosting_weather.py` | Gradient boosting's memory, on generated and weather data |
| `sample_rss.py` | RSS of a process over time, split into anonymous and file-backed pages |
| `batch_agreement.py` | How far the weather forecasts move with the batch size |
| `weather_frame.py`, `replicate_ridge.py` | The weather pipeline rewritten as one in-memory pass, without GardenPipe |
| `diagnostics.py`, `model_diagnostics.py`, `yearly_error.py` | Fit diagnostics |
| `compare_models.py`, `random_features.py`, `feature_width.py` | Model comparisons on the same rows and folds |
| `figure_data.py`, `collect.py` | Gather the results for `scripts/draw_gardenpipe_figures.py` |

`random_features.py` runs through GardenPipe's streaming path. `feature_width.py` is a faster NumPy-only check of the
same idea. Test scores were read only after selection on the validation folds.
