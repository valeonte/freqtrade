#!/bin/bash
# Round 7 driver, resumable: every step skips what is already done (checkpoints under cache/, finished CSVs,
# exported orders), so after a restart just run it again:
#   setsid nohup user_data/candidates/round7/run_round7.sh > user_data/candidates/round7/run_round7.log 2>&1 &
# Niced, numerical libraries and LightGBM at <= 2 threads per process.
cd "$(dirname "$0")/../../.." || exit 1
here=user_data/candidates/round7
py() { OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 19 .env/bin/python -W ignore "$@"; }
log() { echo "$(date -u '+%F %T') $*"; }
mkdir -p "$here/cache"

# study 44 step 1: lookahead guard (2 + 4 processes) and admission
if [ ! -f "$here/features_admitted.json" ]; then
  log "guard"
  for i in 0 1; do py $here/study44_guard.py guard d00 $i 2 > "$here/cache/guard_d00_$i.log" 2>&1 & done
  for i in 0 1 2 3; do py $here/study44_guard.py guard 4h $i 4 > "$here/cache/guard_4h_$i.log" 2>&1 & done
  wait
  py $here/study44_guard.py admit > "$here/results_44_admit.txt" 2>&1 || { log "admit failed"; exit 1; }
fi

# feature caches (one file per series; 4 processes)
log "build caches"
for keys in "d00 d04" "d08 d12" "d16 d20" "4h"; do py $here/study44_screen.py build $keys & done
wait

# study 45 (a) needs only the caches: run it beside the screen
if [ ! -f "$here/results_45a.csv" ]; then
  log "study 45a"
  py $here/study45_models.py > "$here/results_45a.txt" 2>&1 &
fi
if [ ! -f "$here/results_44_cells.csv.gz" ]; then
  log "study 44 screen"
  py $here/study44_screen.py screen > "$here/results_44.txt" 2>&1 || { log "screen failed"; exit 1; }
fi
wait
[ -f "$here/results_45a.csv" ] || { log "45a failed"; exit 1; }

if [ ! -f "$here/results_45b_spa.csv" ]; then
  log "study 45b"
  py $here/study45_combos.py > "$here/results_45b.txt" 2>&1 || { log "45b failed"; exit 1; }
fi
if [ ! -f "$here/results_46.csv" ]; then
  log "study 46"
  py $here/study46_overlays.py > "$here/results_46.txt" 2>&1 || { log "46 failed"; exit 1; }
fi

# study 47 uses the study-44 survivors if any; the standard feature set is wired in only for "none survived"
surv=$(py -c "import pandas as pd; print(int(pd.read_csv('$here/results_44_cells.csv.gz')['survivor'].sum()))")
if [ "$surv" != "0" ]; then
  log "study 44 has $surv survivors: study 47's features must be switched to them before FreqAI; stopping"
  exit 0
fi
log "study 47 FreqAI"
for tr in 20190101-20201231 20210101-20231231 20240101-20260630; do
  for lab in class value; do
    (
      for use in trim veto standalone none; do
        if [ ! -f "$here/orders/freqai_${lab}_${use}_$tr.csv.gz" ]; then
          log "freqai $lab $use $tr"
          $here/run_ft.sh "freqai_${lab}_${use}" "$tr"
        fi
      done
    ) &
  done
  wait
done
log "study 47 report"
py $here/study47_report.py > "$here/results_47.txt" 2>&1
log "all done"
