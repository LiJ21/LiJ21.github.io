#!/bin/bash
# Does peak RSS depend on the page cache, on the sampler, or on both?
cd GardenPipe; PY=.venv/bin/python; N=NOTE; W=WORK; OUT=$W/cache_test.jsonl; rm -f $OUT
one() { # state sampler rows
  local state=$1 sampler=$2 rows=$3 dir=$W/d$(($3 / 1000000))m
  python3 $N/page_cache.py $state $dir
  if [ "$sampler" = yes ]; then
    python3 $N/sample_rss.py $W/rss/cachetest_${state}_$rows.csv $PY $N/measure_memory.py --data $dir --rows $rows --days 10 --tag $state-sampled --out $OUT > /dev/null 2>&1
  else
    $PY $N/measure_memory.py --data $dir --rows $rows --days 10 --tag $state --out $OUT > /dev/null 2>&1
  fi
}
for repeat in 1 2 3; do one cold no 4000000; one warm no 4000000; done
one cold yes 4000000; one warm yes 4000000
for rows in 1000000 10000000; do one cold no $rows; one warm no $rows; done
