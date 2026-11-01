#!/bin/bash
# Freqtrade backtests for round 4: run_ft.sh <config> <name> [timeranges...]
# Output: user_data/candidates/round4/results_freqtrade/<name>_<timerange>.txt
cd "$(dirname "$0")/../../.." || exit 1
cfg=$1; name=$2; shift 2
ranges=${*:-"20190101-20260630 20190101-20201231 20210101-20231231 20240101-20260630"}
out=user_data/candidates/round4/results_freqtrade
mkdir -p "$out"
for tr in $ranges; do
  nice -n 19 .env/bin/freqtrade backtesting -c "$cfg" \
    --datadir user_data/data_bed/binance --timerange "$tr" --strategy-path user_data/strategies \
    --export none --breakdown year 2>/dev/null | grep -vE '^[0-9]{4}-[0-9]{2}-[0-9]{2} ' > "$out/${name}_$tr.txt"
  echo "done $name $tr"
done
