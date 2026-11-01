#!/bin/bash
# Round 8 driver, resumable (each step skips finished outputs; the screens checkpoint under cache/):
#   setsid nohup user_data/candidates/round8/run_round8.sh > user_data/candidates/round8/run_round8.log 2>&1 &
# Niced, numerical libraries at <= 2 threads. Waits for fetch.py's aggTrades months before the main family.
cd "$(dirname "$0")/../../.." || exit 1
here=user_data/candidates/round8
src=user_data/data_bed/external/binance_vision/round8
py() { OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 19 .env/bin/python -u -W ignore "$@"; }
log() { echo "$(date -u '+%F %T') $*"; }
mkdir -p "$here/cache"

[ -f "$here/results_50.csv" ] || { log "study 50"; py $here/study50_calendar.py > "$here/results_50.txt" 2>&1; }
[ -f "$here/results_49.csv" ] || { log "study 49"; py $here/study49_flush.py > "$here/results_49.txt" 2>&1; }
[ -f "$here/results_48_limit.csv.gz" ] || { log "limit note"; py $here/study48_limit.py > "$here/results_48_limit.txt" 2>&1; }

[ -f "$here/cache/depth/names.txt" ] || { log "build depth"; py $here/study48_screen.py build depth || exit 1; }
[ -f "$here/results_48_depth_cells.csv.gz" ] || { log "screen depth"; py $here/study48_screen.py screen depth > "$here/results_48_depth.txt" 2>&1 || { log "depth screen failed"; exit 1; }; }

# the main family needs every aggTrades month 2019-01 -> 2026-06 (180 files)
if ! pgrep -f "round8/fetch.py aggtrades" > /dev/null && [ "$(ls $src/aggtrades/*.parquet 2>/dev/null | wc -l)" -lt 180 ]; then
  log "aggTrades incomplete: fetching"; py $here/fetch.py aggtrades
fi
while [ "$(ls $src/aggtrades/*.parquet 2>/dev/null | wc -l)" -lt 180 ]; do sleep 120; done
[ -f "$here/cache/main/names.txt" ] || { log "build main"; py $here/study48_screen.py build main || exit 1; }
[ -f "$here/results_48_main_cells.csv.gz" ] || { log "screen main"; py $here/study48_screen.py screen main > "$here/results_48_main.txt" 2>&1 || { log "main screen failed"; exit 1; }; }
[ -f "$here/results_48_overlays.csv" ] || { log "overlays"; py $here/study48_overlays.py > "$here/results_48_overlays.txt" 2>&1 || { log "overlays failed"; exit 1; }; }
log "all done"
