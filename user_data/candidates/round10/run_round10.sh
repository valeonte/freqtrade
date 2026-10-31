#!/bin/bash
# Round 10 driver, resumable (each step skips finished outputs; the screens checkpoint under cache/<fam>/):
#   setsid nohup user_data/candidates/round10/run_round10.sh > user_data/candidates/round10/run_round10.log 2>&1 &
# Niced, numerical libraries at <= 2 threads. fetch.py skips files that exist (the option trades were also fetched by
# several `fetch.py deribit <start> <end>` workers at once to save time).
cd "$(dirname "$0")/../../.." || exit 1
here=user_data/candidates/round10
py() { OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 19 .env/bin/python -u -W ignore "$@"; }
log() { echo "$(date -u '+%F %T') $*"; }
mkdir -p "$here/cache"

py $here/fetch.py all || { log "fetch failed"; exit 1; }
for fam in 56 57 58 59; do
  [ -f "$here/cache/$fam/names.txt" ] || { log "build $fam"; py $here/screen.py build $fam || exit 1; }
  [ -f "$here/results_${fam}_cells.csv.gz" ] || { log "screen $fam"; py $here/screen.py screen $fam > "$here/results_${fam}_screen.txt" 2>&1 || { log "screen $fam failed"; exit 1; }; }
done
[ -f "$here/results_overlays_56_58_59.csv" ] || { log "overlays 56 58 59"; py $here/overlays.py 56 58 59 > "$here/results_overlays_56_58_59.txt" 2>&1 || exit 1; }
[ -f "$here/results_overlays_57.csv" ] || { log "overlays 57"; py $here/overlays.py 57 > "$here/results_overlays_57.txt" 2>&1 || exit 1; }
[ -f "$here/orders/tranches6_20240101-20260630.csv.gz" ] || { log "freqtrade"; $here/run_ft.sh > "$here/run_ft.log" 2>&1; }
[ -f "$here/results_60.csv" ] || { log "study 60"; py $here/study60_tranches.py > "$here/results_60.txt" 2>&1 || exit 1; }
[ -f "$here/results_58c_posthoc.txt" ] || py $here/posthoc_58c.py > "$here/results_58c_posthoc.txt" 2>&1
py $here/forward_log.py
log "all done"
