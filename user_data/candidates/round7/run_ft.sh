#!/bin/bash
# Round 7 freqtrade backtests with every order exported: run_ft.sh <config name> [timeranges...]
# Configs in configs/<name>.json. Output: results_freqtrade/<name>_<timerange>.txt and orders/<name>_<timerange>.csv.gz
cd "$(dirname "$0")/../../.." || exit 1
here=user_data/candidates/round7
name=$1; shift
ranges=${*:-"20190101-20201231 20210101-20231231 20240101-20260630"}
mkdir -p "$here/results_freqtrade" "$here/orders" "$here/exports"
for tr in $ranges; do
  exp=$here/exports/${name}_$tr
  rm -rf "$exp" && mkdir -p "$exp"
  OMP_NUM_THREADS=2 nice -n 19 .env/bin/freqtrade backtesting -c "$here/configs/$name.json" \
    --datadir user_data/data_bed/binance --timerange "$tr" --strategy-path user_data/strategies \
    --freqaimodel-path user_data/freqaimodels --export trades --backtest-directory "$exp" --breakdown year \
    --logfile "$exp/freqtrade.log" 2>/dev/null \
    | grep -vE '^[0-9]{4}-[0-9]{2}-[0-9]{2} ' | sed 's/[[:space:]]*$//' > "$here/results_freqtrade/${name}_$tr.txt"
  nice -n 19 .env/bin/python user_data/candidates/round6/export_orders.py "$exp" "$here/orders/${name}_$tr.csv.gz"
done
