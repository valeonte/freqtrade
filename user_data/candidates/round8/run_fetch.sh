#!/bin/bash
# Round 8 downloads, resumable (each output file is skipped once written); one big file at a time:
#   setsid nohup user_data/candidates/round8/run_fetch.sh > user_data/candidates/round8/cache/fetch.log 2>&1 &
cd "$(dirname "$0")/../../.." || exit 1
py() { OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 19 .env/bin/python -W ignore "$@"; }
for step in klines metrics depth aggtrades; do
  echo "$(date -u '+%F %T') $step"
  py user_data/candidates/round8/fetch.py $step || echo "$(date -u '+%F %T') $step FAILED"
done
echo "$(date -u '+%F %T') fetch done"
