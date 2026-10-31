#!/bin/bash
# Round 9 driver, resumable (each step skips finished outputs; the screens checkpoint under cache/<fam>/):
#   setsid nohup user_data/candidates/round9/run_round9.sh > user_data/candidates/round9/run_round9.log 2>&1 &
# Niced, numerical libraries at <= 2 threads. fetch.py skips files that exist.
cd "$(dirname "$0")/../../.." || exit 1
here=user_data/candidates/round9
py() { OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 POLARS_MAX_THREADS=2 nice -n 19 .env/bin/python -u -W ignore "$@"; }
log() { echo "$(date -u '+%F %T') $*"; }
mkdir -p "$here/cache"

py $here/fetch.py all || { log "fetch failed"; exit 1; }
for fam in 52 53 54 55; do
  [ -f "$here/cache/$fam/names.txt" ] || { log "build $fam"; py $here/screen.py build $fam || exit 1; }
  [ -f "$here/results_${fam}_cells.csv.gz" ] || { log "screen $fam"; py $here/screen.py screen $fam > "$here/results_${fam}_screen.txt" 2>&1 || { log "screen $fam failed"; exit 1; }; }
done
[ -f "$here/results_overlays.csv" ] || { log "overlays"; py $here/overlays.py > "$here/results_overlays.txt" 2>&1 || { log "overlays failed"; exit 1; }; }
[ -f "$here/results_53c.csv" ] || { log "cycle sleeve"; py $here/study53_sleeve.py > "$here/results_53c.txt" 2>&1 || { log "sleeve failed"; exit 1; }; }
log "all done"
