#!/usr/bin/env bash
# The same jobs before and after the patches, in one environment. Section 13 of RESULTS.md.
# Nothing is written to a checkout: output goes to OUT, and the data are only read.
#
#   CODE=CHECKOUT PY=PYTHON WORK=DATA OUT=DIR apply_check.sh before    jobs on CODE, published
#   CODE=CHECKOUT PY=PYTHON WORK=DATA OUT=DIR apply_check.sh after     the same jobs on CODE, patched
#   PUBLISHED=CHECKOUT PATCHED=CHECKOUT PY=PYTHON WORK=DATA OUT=DIR apply_check.sh rotate
#   PUBLISHED=CHECKOUT PATCHED=CHECKOUT LARGER=CHECKOUT PY=PYTHON WORK=DATA OUT=DIR apply_check.sh batch
#   PUBLISHED=CHECKOUT PATCHED=CHECKOUT PY=PYTHON WORK=DATA OUT=DIR apply_check.sh slope
#   PATCHED=CHECKOUT PY=PYTHON OLD_PY=PYTHON WORK=DATA OUT=DIR apply_check.sh versions
#   CODE=CHECKOUT LABEL=NAME PY=PYTHON WORK=DATA OUT=DIR apply_check.sh panel
#
# WORK comes from run_experiments.sh and the generate phase of run_followups.sh: d4m with 30 dates or
# more, d20m and d40m with five. Each checkout has run examples/weather/prepare.py. rotate runs the
# 30-date example from each checkout in turn, reading the page cache before and after each run. batch
# runs the 40M-row job in both modes, four settings in turn and then in reverse. slope runs the fixed
# look-ahead job at 200,000-row batches. LARGER is PATCHED with larger-time-chunks.patch on top.
# versions runs the README's table from one checkout on two versions of Polars, in turn. Only peak
# memory is read from it, so it asks for all the data to be resident around each run, not for an idle
# machine. panel runs MultiSourceLoader on the fixed look-ahead job, with one shared file and with one
# file per station; it needs p4m, p20m and p40m from panel_data.py, and LABEL names the code in its record.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PHASE=$1
RUN=$OUT/$PHASE
mkdir -p "$RUN"
cd "$RUN" || exit 1

stamp() { echo "=== $(date -Is) $*"; }

timed() {
  local name=$1
  shift
  python3 "$HERE/quiet.py" wait
  /usr/bin/time -o "$RUN/$name.time" -f '%M %e' "$@" > "$RUN/$name.log" 2>&1
  echo "$name exit=$? $(tail -1 "$RUN/$name.time")"
}

jobs() {
  export PYTHONPATH=$CODE
  stamp "code under test: $(sha256sum "$CODE/gardenpipe/data.py" | cut -c1-12)"
  "$PY" -c 'import polars; print("polars", polars.__version__)'

  stamp "examples/minimal.py, the table in the GardenPipe README"
  python3 "$HERE/page_cache.py" warm "$WORK/d4m" | tail -1
  echo "first 30 dates: $(python3 "$HERE/page_resident.py" "$WORK/d4m" 30) MiB resident"
  timed minimal_10_warm "$PY" "$CODE/examples/minimal.py" --days 10 --data "$WORK/d4m"
  timed minimal_30_warm "$PY" "$CODE/examples/minimal.py" --days 30 --data "$WORK/d4m"
  python3 "$HERE/page_cache.py" cold "$WORK/d4m" | tail -1
  timed minimal_10_cold "$PY" "$CODE/examples/minimal.py" --days 10 --data "$WORK/d4m"

  stamp "examples/weather/train.py"
  local batch run m
  for batch in 5000 20000 1000000; do
    timed "weather_$batch" "$PY" "$CODE/examples/weather/train.py" --batch-rows "$batch" \
      --data-dir "$CODE/data/jena" --runs-dir "$RUN/weather_$batch"
  done

  stamp "fixed look-ahead, five dates"
  for run in 20:60s 40:30s; do
    m=${run%:*}
    python3 "$HERE/quiet.py" wait
    python3 "$HERE/page_cache.py" cold "$WORK/d${m}m" | tail -1
    "$PY" "$HERE/measure_memory.py" --data "$WORK/d${m}m" --rows $((m * 1000000)) --days 5 \
      --horizon "${run#*:}" --tag "apply-$PHASE" --page-cache cold --out "$RUN/fixed.jsonl" > "$RUN/fixed_$m.log" 2>&1
    echo "fixed_$m exit=$?"
  done
  stamp done
}

rotate() {
  local resident_dir=$WORK/d4m i=0 side src start code
  available() { awk '/MemAvailable/ {printf "%.0f", $2/1024}' /proc/meminfo; }
  for side in published patched patched published; do
    i=$((i + 1))
    case $side in
      published) src=$PUBLISHED ;;
      patched) src=$PATCHED ;;
    esac
    python3 "$HERE/quiet.py" wait
    python3 "$HERE/page_cache.py" warm "$resident_dir" | tail -1
    start="resident $(python3 "$HERE/page_resident.py" "$resident_dir" 30) MiB, available $(available) MiB"
    PYTHONPATH=$src /usr/bin/time -o "$RUN/$i.$side.time" -f '%M %e' "$PY" "$src/examples/minimal.py" \
      --days 30 --data "$resident_dir" > "$RUN/$i.$side.log" 2>&1
    code=$?
    echo "$i $side $(sha256sum "$src/gardenpipe/data.py" | cut -c1-12) exit=$code | start: $start | end: resident $(python3 "$HERE/page_resident.py" "$resident_dir" 30) MiB, available $(available) MiB | $(grep -E 'peak RSS' "$RUN/$i.$side.log" | sed 's/.*peak/peak/') | $(awk '{print $2}' "$RUN/$i.$side.time") s | $(grep 'test R' "$RUN/$i.$side.log")"
  done
}

# one_run MODE LABEL CHECKOUT BATCH BUDGET MILLIONS DATES HORIZON
one_run() {
  local code
  python3 "$HERE/quiet.py" wait
  python3 "$HERE/page_cache.py" cold "$WORK/d${6}m" | tail -1
  PYTHONPATH=$3 "$PY" "$HERE/measure_memory.py" --data "$WORK/d${6}m" --rows $(($6 * 1000000)) --days "$7" --mode "$1" \
    --batch "$4" --buffer-mib "$5" --horizon "$8" --tag "$PHASE:$2" --page-cache cold --out "$RUN/runs.jsonl" > "$RUN/last.log" 2>&1
  code=$?
  echo "$1 $2 ${6}M exit=$code"
}

batch() {
  local round mode setting
  for round in "published patched batch200k larger" "larger batch200k patched published"; do
    for mode in materialize stream; do
      for setting in $round; do
        case $setting in
          published) one_run "$mode" published "$PUBLISHED" 100000 64 4 10 5m ;;
          patched) one_run "$mode" patched "$PATCHED" 100000 64 4 10 5m ;;
          batch200k) one_run "$mode" batch200k "$PATCHED" 200000 69 4 10 5m ;;
          larger) one_run "$mode" larger "$LARGER" 100000 64 4 10 5m ;;
        esac
      done
    done
  done
}

slope() {
  local job
  for job in 4:5m 20:60s 40:30s; do
    one_run stream published "$PUBLISHED" 200000 69 "${job%:*}" 5 "${job#*:}"
    one_run stream patched "$PATCHED" 200000 69 "${job%:*}" 5 "${job#*:}"
  done
}

versions() {
  local dir=$WORK/d4m i=0 side py version days name start code
  for side in new old old new; do
    i=$((i + 1))
    case $side in
      new) py=$PY ;;
      old) py=$OLD_PY ;;
    esac
    version=$("$py" -c 'import polars; print(polars.__version__)')
    for days in 10 30; do
      name=$i.$version.$days
      python3 "$HERE/page_cache.py" warm "$dir" | tail -1
      start=$(python3 "$HERE/page_resident.py" "$dir" "$days")
      PYTHONPATH=$PATCHED /usr/bin/time -o "$RUN/$name.time" -f '%M %e' "$py" "$PATCHED/examples/minimal.py" \
        --days "$days" --data "$dir" > "$RUN/$name.log" 2>&1
      code=$?
      echo "$name $(sha256sum "$PATCHED/gardenpipe/data.py" | cut -c1-12) exit=$code | resident $start then $(python3 "$HERE/page_resident.py" "$dir" "$days") MiB | $(grep -E 'peak RSS' "$RUN/$name.log" | sed 's/.*peak/peak/') | $(awk '{print $2}' "$RUN/$name.time") s | $(grep 'test R' "$RUN/$name.log")"
    done
  done
}

panel() {
  local job m files code
  export PYTHONPATH=$CODE
  for job in ${JOBS:-4:5m 20:60s 40:30s}; do
    m=${job%:*}
    for files in ${FILES:-shared each}; do
      python3 "$HERE/quiet.py" wait
      python3 "$HERE/page_cache.py" cold "$WORK/p${m}m" | tail -1
      "$PY" "$HERE/measure_panel.py" --data "$WORK/p${m}m" --rows $((m * 1000000)) --days 5 --files "$files" \
        --horizon "${job#*:}" --tag "panel:$LABEL" --page-cache cold --out "$RUN/runs.jsonl" > "$RUN/last.log" 2>&1
      code=$?
      echo "$LABEL ${m}M $files exit=$code"
    done
  done
}

case $PHASE in
  before | after) jobs ;;
  rotate) rotate ;;
  batch) batch ;;
  slope) slope ;;
  versions) versions ;;
  panel) panel ;;
  *) echo "before, after, rotate, batch, slope, versions, or panel"; exit 1 ;;
esac
