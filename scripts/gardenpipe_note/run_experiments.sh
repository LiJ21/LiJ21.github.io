#!/bin/bash
# Reproduce every memory measurement in RESULTS.md. From a GardenPipe checkout, with its environment synced:
#   NOTE=/path/to/scripts/gardenpipe_note WORK=/fast/disk bash "$NOTE/run_experiments.sh"
# Takes about two and a half hours on 12 cores, and needs about 30 GiB of disk and 19 GiB of free RAM.
# Keep the machine otherwise idle: every result records how much CPU everything else used.
set -u
PY=.venv/bin/python
SAMPLE="python3 $NOTE/sample_rss.py"
CAP="systemd-run --user --scope --quiet -p MemoryMax=1G -p MemorySwapMax=0"
OUT=$WORK/results.jsonl
mkdir -p "$WORK/rss"
rm -f "$OUT"
phase() { echo "=== $(date -Is) $*"; }
# One measured run in a fresh process: rows per date first, flags after, command prefix in $PREFIX.
# The files start out of the page cache unless CACHE=warm. Data larger than RAM cannot all be cached,
# so cold reads are the case a bound has to cover, and they use more memory than warm ones.
run() {
  local rows=$1 state=${CACHE:-cold} dir="$WORK/d$(($1 / 1000000))m"
  shift
  python3 "$NOTE/page_cache.py" "$state" "$dir"
  ${PREFIX:-} "$PY" "$NOTE/measure_memory.py" --data "$dir" --rows "$rows" --page-cache "$state" --out "$OUT" "$@"
}

phase "generating data, in its own process"
for spec in "4000000 90" "10000000 100" "1000000 10" "2000000 10" "6000000 10" "8000000 10" "12000000 10" "16000000 10" "20000000 10"; do
  read -r rows days <<< "$spec"
  "$PY" "$NOTE/generate_data.py" --data "$WORK/d$((rows / 1000000))m" --rows "$rows" --days "$days"
done

phase "the interpreter and libraries alone"
"$PY" -c "import resource, numpy, polars, gardenpipe.buffered, gardenpipe.data, gardenpipe.features, gardenpipe.model, gardenpipe.pipeline, gardenpipe.score; print('imports only, peak RSS MiB:', round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1))"

phase "rows per date, with ten dates"
for rows in 1000000 2000000 4000000 6000000 8000000 10000000 12000000 16000000 20000000; do
  PREFIX="$SAMPLE $WORK/rss/density_$((rows / 1000000))m.csv" run "$rows" --days 10 --tag density
done

phase "the same job with its files out of the page cache and in it"
for repeat in 1 2 3; do
  CACHE=cold run 4000000 --days 10 --tag cache
  CACHE=warm run 4000000 --days 10 --tag cache
done

phase "number of dates, streamed and materialized"
for days in 5 10 20 30 60 90; do
  run 4000000 --days "$days" --mode stream --tag scale
  run 4000000 --days "$days" --mode materialize --tag scale
done

phase "three repeats of one job, for run-to-run spread"
for repeat in 1 2 3; do run 4000000 --days 30 --mode stream --tag repeat; done

phase "batch size, with a budget of at least three generous batches"
for batch in 25000 50000 100000 200000 400000 800000 1600000; do
  budget=$(python3 -c "print(max(64, round($batch * 120 * 3 / 2**20)))")
  run 4000000 --days 10 --batch "$batch" --buffer-mib "$budget" --tag batch
done

phase "prefetch budget"
for budget in 16 32 64 128 256 512 1024; do run 4000000 --days 10 --buffer-mib "$budget" --tag buffer; done

phase "workers"
for workers in 1 2 4 8; do run 4000000 --days 10 --workers "$workers" --tag workers; done

phase "a budget too small to make progress"
start=$(date +%s.%N)
run 4000000 --days 10 --buffer-mib 1 --tag failfast > "$WORK/failfast.log" 2>&1
echo "exit status $? after $(python3 -c "import time; print(round(time.time() - $start, 1))") s" | tee -a "$WORK/failfast.log"

phase "the same job under a hard limit of 1 GiB, with swap disabled"
PREFIX="$SAMPLE $WORK/rss/cap_stream.csv $CAP" run 4000000 --days 30 --mode stream --tag cap
echo "streamed run exit status $?"
PREFIX="$SAMPLE $WORK/rss/cap_mat.csv $CAP" run 4000000 --days 30 --mode materialize --tag cap
echo "materialized run exit status $? (247 is -9, SIGKILL, as sample_rss.py passes it on)"

phase "one billion rows under the same limit"
PREFIX="$SAMPLE $WORK/rss/billion.csv $CAP" run 10000000 --days 100 --mode stream --tag billion
echo "billion-row run exit status $?"

phase "gradient boosting, in core and with external memory"
for days in 10 30; do
  python3 "$NOTE/page_cache.py" cold "$WORK/d4m"
  "$PY" "$NOTE/measure_boosting.py" --data "$WORK/d4m" --days "$days" --cache "$WORK/xgb" --out "$OUT"
  rm -rf "$WORK/xgb"
  python3 "$NOTE/page_cache.py" cold "$WORK/d4m"
  $SAMPLE "$WORK/rss/xgb_ext_$days.csv" "$PY" "$NOTE/measure_boosting.py" --data "$WORK/d4m" --days "$days" --external --cache "$WORK/xgb" --out "$OUT"
  rm -rf "$WORK/xgb"
done

phase "gradient boosting under the 1 GiB limit, 40 million rows"
python3 "$NOTE/page_cache.py" cold "$WORK/d4m"
$SAMPLE "$WORK/rss/xgb_cap_core.csv" $CAP "$PY" "$NOTE/measure_boosting.py" --data "$WORK/d4m" --days 10 --tag xgb-cap --cache "$WORK/xgb" --out "$OUT"
echo "in-core boosting exit status $?"
rm -rf "$WORK/xgb"
python3 "$NOTE/page_cache.py" cold "$WORK/d4m"
$SAMPLE "$WORK/rss/xgb_cap_ext.csv" $CAP "$PY" "$NOTE/measure_boosting.py" --data "$WORK/d4m" --days 10 --external --tag xgb-cap --cache "$WORK/xgb" --out "$OUT"
echo "external-memory boosting exit status $?"
rm -rf "$WORK/xgb"
phase "done"
