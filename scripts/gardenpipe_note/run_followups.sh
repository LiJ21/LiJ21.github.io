#!/bin/bash
# The follow-up measurements in RESULTS.md, which ask why the peak moves with rows per date.
# Run after run_experiments.sh, with the same NOTE and WORK:
#   NOTE=/path/to/scripts/gardenpipe_note WORK=/fast/disk bash "$NOTE/run_followups.sh" [phase ...]
# With no phases it runs PHASES below, which measure the published commit. The later phases need other
# checkouts, and each refuses to run from the wrong one:
#   published commit:           the default PHASES, limit_before
#   any checkout:               slow_stream slow_epoch slow_epoch_threads slow_stream_threads chunk_query,
#                               which run Polars alone
#   window-filter.patch:        fix_curve fix_flat
#   and then time-chunks.patch: chunk_flat chunk_curve chunk_threads chunk_changes chunk_budget
#                               chunk_repeats chunk_boosting chunk_billion limit_after
#   and then larger-time-chunks.patch: chunk_wide
#   each checkout in turn:      rotation
# A run counts only if the rest of the machine stayed idle; otherwise its record goes to
# contaminated.jsonl and it is run again.
set -u
PY=.venv/bin/python
SAMPLE="python3 $NOTE/sample_rss.py"
OUT=$WORK/results_followup.jsonl
PHASES="generate reader mechanism curve lookahead threads settings warm budget boosting"
mkdir -p "$WORK/rss"
phase() { echo "=== $(date -Is) $*"; }

# The phases of the default list measure the published loader.
published() {
  ! grep -q 'getattr(dtype, "time_zone", None)\|_time_chunks' gardenpipe/data.py || { echo "run this from a checkout of the published commit"; exit 1; }
}

# measured STATE DIR COMMAND...: settings in $ENVS, a command prefix in $PREFIX
measured() {
  local state=$1 dir=$2 last=$WORK/last.jsonl try
  shift 2
  for try in 1 2 3 4 5 6; do
    python3 "$NOTE/quiet.py" wait
    python3 "$NOTE/page_cache.py" "$state" "$dir"
    rm -f "$last"
    env ${ENVS:-} ${PREFIX:-} "$PY" "$@" --page-cache "$state" --out "$last"
    python3 "$NOTE/quiet.py" keep "$last" "$OUT" "$WORK/contaminated.jsonl" && return 0
  done
  echo "gave up after six attempts: $*"
}

# pipeline ROWS_IN_MILLIONS FLAGS...: ridge unless the flags say otherwise, five dates unless they say otherwise
pipeline() {
  local millions=$1
  shift
  measured "${CACHE:-cold}" "$WORK/d${millions}m" "$NOTE/measure_memory.py" --data "$WORK/d${millions}m" --rows $((millions * 1000000)) "$@"
}

generate() {
  phase "rows per date beyond 20 million"
  python3 "$NOTE/quiet.py" wait
  "$PY" "$NOTE/generate_data.py" --data "$WORK/d40m" --rows 40000000 --days 5
  "$PY" "$NOTE/generate_data.py" --data "$WORK/d80m" --rows 80000000 --days 5
}

reader() {
  phase "Polars alone on one file, no GardenPipe"
  local millions query
  for millions in 1 4 20 40 80; do
    for query in max stream; do
      measured cold "$WORK/d${millions}m" "$NOTE/reader_memory.py" --file "$WORK/d${millions}m/sensor_2026-01-05.parquet" \
        --rows $((millions * 1000000)) --query "$query"
    done
  done
}

mechanism() {
  published
  phase "one change at a time, at 4 and 20 million rows per date, five dates"
  local millions
  for millions in 4 20; do
    pipeline "$millions" --days 5 --tag mech-base
    pipeline "$millions" --days 5 --tag mech-no-model --model discard
    ENVS="_RJEM_MALLOC_CONF=dirty_decay_ms:0,muzzy_decay_ms:0" pipeline "$millions" --days 5 --tag mech-no-decay
    ENVS="POLARS_ROW_GROUP_PREFETCH_SIZE=8" pipeline "$millions" --days 5 --tag mech-prefetch-8
    ENVS="POLARS_MAX_THREADS=4" pipeline "$millions" --days 5 --tag mech-threads-4
  done
}

curve() {
  published
  phase "rows per date beyond 20 million, five dates, with mech-base supplying 4 and 20 million"
  local millions
  for millions in 1 10 40 80; do
    PREFIX="$SAMPLE $WORK/rss/density5_${millions}m.csv" pipeline "$millions" --days 5 --tag density5
  done
}

# A five-minute horizon is 13,889 rows at 4 million rows per date and 277,778 at 80 million.
lookahead() {
  published
  phase "the same look-ahead in rows at every density, and a longer one at low density"
  pipeline 20 --days 5 --horizon 60s --tag lookahead
  pipeline 40 --days 5 --horizon 30s --tag lookahead
  pipeline 80 --days 5 --horizon 15s --tag lookahead
  pipeline 4 --days 5 --horizon 25m --tag lookahead
}

threads() {
  published
  phase "Polars threads, with mech-base supplying 20"
  local n
  for n in 1 2 4 8 12; do
    ENVS="POLARS_MAX_THREADS=$n" pipeline 4 --days 5 --tag threads
  done
}

settings() {
  published
  phase "read-ahead alone in Polars, and the changes together"
  ENVS="POLARS_ROW_GROUP_PREFETCH_SIZE=8" measured cold "$WORK/d80m" "$NOTE/reader_memory.py" \
    --file "$WORK/d80m/sensor_2026-01-05.parquet" --rows 80000000 --query stream --tag reader-prefetch-8
  local millions
  for millions in 4 20; do
    ENVS="POLARS_MAX_THREADS=4 POLARS_ROW_GROUP_PREFETCH_SIZE=8" pipeline "$millions" --days 5 --tag combined-t4-p8
    ENVS="POLARS_MAX_THREADS=4 POLARS_ROW_GROUP_PREFETCH_SIZE=8 _RJEM_MALLOC_CONF=dirty_decay_ms:0,muzzy_decay_ms:0" \
      pipeline "$millions" --days 5 --tag combined-t4-p8-d0
  done
}

warm() {
  published
  phase "does turning off deferred reads make a warm run behave like a cold one?"
  CACHE=warm pipeline 4 --days 5 --tag warm
  CACHE=warm ENVS="POLARS_FILE_DEFER_CACHED_READS=0" pipeline 4 --days 5 --tag warm-no-defer
}

budget() {
  published
  phase "a consumer slower than the producers, so that the queue fills"
  local mib
  for mib in 16 64 256 1024; do
    pipeline 4 --days 5 --buffer-mib "$mib" --model discard --consume-ms 300 --tag slow-consumer
  done
}

# boost_limit TAG: a killed run leaves no record, only its trace and its exit status.
boost_limit() {
  phase "boosting under a 2 GiB limit, between the two modes' peaks, 40 million rows: $1"
  local cap="systemd-run --user --scope --quiet -p MemoryMax=2G -p MemorySwapMax=0" kind flag
  for kind in core ext; do
    flag=""
    [ "$kind" = ext ] && flag="--external"
    python3 "$NOTE/quiet.py" wait
    python3 "$NOTE/page_cache.py" cold "$WORK/d4m"
    $SAMPLE "$WORK/rss/${1//-/_}_$kind.csv" $cap "$PY" "$NOTE/measure_boosting.py" --data "$WORK/d4m" --days 10 $flag \
      --tag "$1" --cache "$WORK/xgb" --out "$OUT"
    echo "boosting $1 $kind exit status $?"
    rm -rf "$WORK/xgb"
  done
}
boosting() { published; boost_limit xgb-2g; }

# The phases below measure window-filter.patch, so they run from a checkout that has it applied.
patched() {
  grep -q 'getattr(dtype, "time_zone", None)' gardenpipe/data.py || { echo "apply window-filter.patch to this checkout first"; exit 1; }
}

fix_curve() {
  patched
  phase "the time bound on the column itself: rows per date, five dates"
  local millions
  for millions in 1 4 10 20 40 80; do
    PREFIX="$SAMPLE $WORK/rss/fix_density5_${millions}m.csv" pipeline "$millions" --days 5 --tag fix-curve
  done
}

# Rows per date and horizon that give 13,888 rows of look-ahead.
SAME_LOOKAHEAD="4:5m 20:60s 40:30s 80:15s"

# If read-ahead and look-ahead are the whole rise, holding both fixed leaves nothing to rise.
fix_flat() {
  patched
  phase "read-ahead of 8 row groups and 13,888 rows of look-ahead at every density"
  local run
  for run in $SAME_LOOKAHEAD; do
    ENVS="POLARS_ROW_GROUP_PREFETCH_SIZE=8" PREFIX="$SAMPLE $WORK/rss/fix_flat_${run%:*}m.csv" \
      pipeline "${run%:*}" --days 5 --horizon "${run#*:}" --tag fix-flat
  done
}

slow_stream() {
  phase "Polars alone, with the time stream taken as slowly as the pipeline takes it"
  local millions file
  for millions in 4 20 40 80; do
    file=$WORK/d${millions}m/sensor_2026-01-05.parquet
    PREFIX="$SAMPLE $WORK/rss/slow_stream_${millions}m.csv" measured cold "$WORK/d${millions}m" "$NOTE/reader_memory.py" \
      --file "$file" --rows $((millions * 1000000)) --query stream --pause-ms 200 --tag slow-stream
    ENVS="POLARS_ROW_GROUP_PREFETCH_SIZE=8" PREFIX="$SAMPLE $WORK/rss/slow_stream_p8_${millions}m.csv" \
      measured cold "$WORK/d${millions}m" "$NOTE/reader_memory.py" \
      --file "$file" --rows $((millions * 1000000)) --query stream --pause-ms 200 --tag slow-stream-p8
  done
}

# The same, selecting the expression GardenPipe selects rather than the bare column.
slow_epoch() {
  phase "Polars alone, the slow stream over the expression GardenPipe uses"
  local millions file
  for millions in ${SLOW:-4 20 40 80}; do
    file=$WORK/d${millions}m/sensor_2026-01-05.parquet
    PREFIX="$SAMPLE $WORK/rss/slow_epoch_${millions}m.csv" measured cold "$WORK/d${millions}m" "$NOTE/reader_memory.py" \
      --file "$file" --rows $((millions * 1000000)) --query stream --pause-ms 200 --column epoch --tag slow-epoch
    ENVS="POLARS_ROW_GROUP_PREFETCH_SIZE=8" PREFIX="$SAMPLE $WORK/rss/slow_epoch_p8_${millions}m.csv" \
      measured cold "$WORK/d${millions}m" "$NOTE/reader_memory.py" \
      --file "$file" --rows $((millions * 1000000)) --query stream --pause-ms 200 --column epoch --tag slow-epoch-p8
  done
}

# Does what the expression keeps in memory depend on the number of Polars threads?
slow_epoch_threads() {
  phase "Polars alone, the slow stream over the expression, four threads"
  local file=$WORK/d40m/sensor_2026-01-05.parquet
  ENVS="POLARS_MAX_THREADS=4" PREFIX="$SAMPLE $WORK/rss/slow_epoch_t4_40m.csv" measured cold "$WORK/d40m" "$NOTE/reader_memory.py" \
    --file "$file" --rows 40000000 --query stream --pause-ms 200 --column epoch --tag slow-epoch-t4
  ENVS="POLARS_MAX_THREADS=4 POLARS_ROW_GROUP_PREFETCH_SIZE=8" PREFIX="$SAMPLE $WORK/rss/slow_epoch_t4_p8_40m.csv" \
    measured cold "$WORK/d40m" "$NOTE/reader_memory.py" \
    --file "$file" --rows 40000000 --query stream --pause-ms 200 --column epoch --tag slow-epoch-t4-p8
}

slow_stream_threads() {
  phase "Polars alone, the slow stream over the bare column, four threads"
  local file=$WORK/d40m/sensor_2026-01-05.parquet
  ENVS="POLARS_MAX_THREADS=4" measured cold "$WORK/d40m" "$NOTE/reader_memory.py" \
    --file "$file" --rows 40000000 --query stream --pause-ms 200 --tag slow-stream-t4
  ENVS="POLARS_MAX_THREADS=4 POLARS_ROW_GROUP_PREFETCH_SIZE=8" measured cold "$WORK/d40m" "$NOTE/reader_memory.py" \
    --file "$file" --rows 40000000 --query stream --pause-ms 200 --tag slow-stream-t4-p8
}

chunk_query() {
  phase "what one chunk of times costs, and whether select and slice can change places"
  python3 "$NOTE/quiet.py" wait
  "$PY" "$NOTE/chunk_query.py" "$WORK/d4m/sensor_2026-01-05.parquet"
  POLARS_MAX_THREADS=1 "$PY" "$NOTE/chunk_query.py" "$WORK/d4m/sensor_2026-01-05.parquet"
  "$PY" "$NOTE/chunk_query.py" "$WORK/d80m/sensor_2026-01-05.parquet"
}

# Run from each checkout in turn, so that drift between hours cannot pass for the effect of a patch.
rotation() {
  phase "ten dates, materialized and streamed, loader $("$PY" -c "import hashlib; print(hashlib.sha256(open('gardenpipe/data.py', 'rb').read()).hexdigest()[:12])")"
  pipeline 4 --days 10 --mode materialize --tag rotation
  pipeline 4 --days 10 --mode stream --tag rotation
}

# The phases below measure time-chunks.patch on top of window-filter.patch.
chunked() {
  grep -q '_time_chunks' gardenpipe/data.py || { echo "apply time-chunks.patch to this checkout first"; exit 1; }
}

chunk_flat() {
  chunked
  phase "no query held open across a date, 13,888 rows of look-ahead at every density"
  local run
  for run in $SAME_LOOKAHEAD; do
    PREFIX="$SAMPLE $WORK/rss/chunk_flat_${run%:*}m.csv" pipeline "${run%:*}" --days 5 --horizon "${run#*:}" --tag chunk-flat
  done
}

chunk_curve() {
  chunked
  phase "no query held open, a five-minute horizon, so that look-ahead grows with density"
  local millions
  for millions in 1 4 10 20 40 80; do
    PREFIX="$SAMPLE $WORK/rss/chunk_curve_${millions}m.csv" pipeline "$millions" --days 5 --tag chunk-curve
  done
}

# The remaining knobs with both patches, each compared with the chunk-flat and chunk-curve runs.
chunk_threads() {
  chunked
  phase "Polars threads with no query held open"
  local n
  for n in 1 2 4 8 12; do
    ENVS="POLARS_MAX_THREADS=$n" pipeline 4 --days 5 --tag chunk-threads
  done
  ENVS="POLARS_MAX_THREADS=4" pipeline 80 --days 5 --horizon 15s --tag chunk-threads
}

chunk_changes() {
  chunked
  phase "one change at a time with no query held open"
  local millions
  for millions in 4 20; do
    pipeline "$millions" --days 5 --tag chunk-no-model --model discard
    ENVS="_RJEM_MALLOC_CONF=dirty_decay_ms:0,muzzy_decay_ms:0" pipeline "$millions" --days 5 --tag chunk-no-decay
    ENVS="POLARS_MAX_THREADS=4 _RJEM_MALLOC_CONF=dirty_decay_ms:0,muzzy_decay_ms:0" pipeline "$millions" --days 5 --tag chunk-t4-d0
  done
}

chunk_budget() {
  chunked
  phase "a slow consumer with no query held open"
  local mib
  for mib in 16 64 256 1024; do
    pipeline 4 --days 5 --buffer-mib "$mib" --model discard --consume-ms 300 --tag chunk-slow-consumer
  done
}

# 8 million rows stood out in the ten-date grid, so repeat it and the sizes either side.
chunk_repeats() {
  chunked
  phase "ten dates at 6, 8 and 10 million rows, three times each, to see how far a peak moves between runs"
  local repeat millions
  for repeat in 1 2 3; do
    for millions in 6 8 10; do
      pipeline "$millions" --days 10 --tag chunk-repeat
    done
  done
}

chunk_boosting() { chunked; boost_limit chunk-xgb-2g; }

# Fewer queries for the times: does holding more of them cost memory at high density?
chunk_wide() {
  grep -q '_TIME_CHUNK_ROWS' gardenpipe/data.py || { echo "apply larger-time-chunks.patch to this checkout first"; exit 1; }
  phase "a million times per query at 80 million rows per date, with both horizons"
  PREFIX="$SAMPLE $WORK/rss/chunk_wide_flat_80m.csv" pipeline 80 --days 5 --horizon 15s --tag chunk-wide
  PREFIX="$SAMPLE $WORK/rss/chunk_wide_curve_80m.csv" pipeline 80 --days 5 --tag chunk-wide
}

# The billion-row job again, to see how far its peak moves between runs.
chunk_billion() {
  chunked
  phase "the billion-row job again, under the 1 GiB limit"
  local cap="systemd-run --user --scope --quiet -p MemoryMax=1G -p MemorySwapMax=0"
  python3 "$NOTE/quiet.py" wait
  python3 "$NOTE/page_cache.py" cold "$WORK/d10m"
  $SAMPLE "$WORK/rss/chunk_billion.csv" $cap "$PY" "$NOTE/measure_memory.py" --data "$WORK/d10m" --rows 10000000 --days 100 \
    --mode stream --tag chunk-billion --page-cache cold --out "$OUT"
  echo "chunk_billion exit status $?"
}

# limit80 NAME: a killed run leaves no record, only its trace and its exit status.
limit80() {
  phase "80 million rows per date under the 1 GiB limit: $1"
  local cap="systemd-run --user --scope --quiet -p MemoryMax=1G -p MemorySwapMax=0"
  python3 "$NOTE/quiet.py" wait
  python3 "$NOTE/page_cache.py" cold "$WORK/d80m"
  $SAMPLE "$WORK/rss/limit80_$1.csv" $cap "$PY" "$NOTE/measure_memory.py" --data "$WORK/d80m" --rows 80000000 --days 5 \
    --tag "limit80-$1" --page-cache cold --out "$OUT"
  echo "limit80 $1 exit status $?"
}
limit_before() { published; limit80 pinned; }
limit_after() { chunked; limit80 patched; }

for name in ${@:-$PHASES}; do "$name"; done
phase "done"
