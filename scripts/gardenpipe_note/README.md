# GardenPipe note: experiments

The scripts behind the note *Arbitrarily large data, bounded memory*. They run against
[GardenPipe](https://github.com/LiJ21/GardenPipe) at commit `9bc5e3e`, on Linux with Python 3.12 and Polars 2.1.

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
| `run_experiments.sh` | Every memory measurement, in about 2.5 hours |
| `summarize.py` | Print the memory results as the tables in `RESULTS.md` |
| `generate_data.py` | Write the generated dataset, in its own process |
| `page_cache.py` | Put a dataset in or out of the page cache before a run |
| `measure_memory.py`, `run_record.py` | One measured run in a fresh process, and what it records about itself |
| `measure_boosting.py`, `boosting_weather.py` | Gradient boosting's memory, on generated and weather data |
| `sample_rss.py` | RSS of a process over time, split into anonymous and file-backed pages |
| `batch_agreement.py` | How far the weather forecasts move with the batch size |
| `weather_frame.py`, `replicate_ridge.py` | The weather pipeline rewritten as one in-memory pass, without GardenPipe |
| `diagnostics.py`, `model_diagnostics.py`, `yearly_error.py` | Fit diagnostics |
| `compare_models.py`, `random_features.py`, `feature_width.py` | Model comparisons on the same rows and folds |
| `figure_data.py`, `collect.py` | Gather the results for `scripts/draw_gardenpipe_figures.py` |

`random_features.py` runs through GardenPipe's streaming path. `feature_width.py` is a faster NumPy-only check of the
same idea. Test scores were read only after selection on the validation folds.
