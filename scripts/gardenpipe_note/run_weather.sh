#!/bin/bash
# Reproduce every weather result in RESULTS.md. From a GardenPipe checkout, with its environment synced:
#   NOTE=/path/to/scripts/gardenpipe_note WORK=/fast/disk bash "$NOTE/run_weather.sh"
# Downloads 13 MiB and takes about 15 minutes on 12 cores. Timings mean something only on an idle machine.
set -u
PY=.venv/bin/python
mkdir -p "$WORK"
rm -f "$WORK/rff.jsonl" "$WORK/boosting_weather.jsonl"
phase() { echo "=== $(date -Is) $*"; }

phase "the GardenPipe example, at its default batch of 20,000 rows"
"$PY" examples/weather/prepare.py
"$PY" examples/weather/train.py
"$PY" examples/weather/report.py

phase "other batch sizes, and the agreement between them"
for batch in 5000 1000000; do
  "$PY" examples/weather/train.py --batch-rows "$batch" --runs-dir "$WORK/weather_$batch"
done
"$PY" "$NOTE/batch_agreement.py" "$WORK"

phase "the same pipeline without GardenPipe"
"$PY" "$NOTE/replicate_ridge.py"

phase "fit diagnostics"
"$PY" "$NOTE/yearly_error.py"
"$PY" "$NOTE/diagnostics.py" runs/weather/predictions.parquet "$WORK"
"$PY" "$NOTE/worst_forecast.py"

phase "model comparison"
"$PY" "$NOTE/compare_models.py" "$WORK"
"$PY" "$NOTE/model_diagnostics.py" "$WORK"
"$PY" "$NOTE/feature_width.py"

phase "time and memory by model"
"$PY" "$NOTE/boosting_weather.py" "$WORK" | grep '^{' | tee -a "$WORK/boosting_weather.jsonl"
for spec in "0 0" "500 0" "2000 0" "2000 1" "2000 2" "2000 3" "4000 0"; do
  read -r width seed <<< "$spec"
  "$PY" "$NOTE/random_features.py" --D "$width" --seed "$seed" --out "$WORK/rff.jsonl" --pred-dir "$WORK"
done

phase "figure data"
"$PY" "$NOTE/figure_data.py" "$WORK"
phase "done"
