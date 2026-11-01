#!/bin/bash
# Study 62 freqtrade backtests with every order exported (round 10's pattern): run_ft.sh [config names...]
# Configs in configs/<name>.json, datadir from ft_data.py. Output: results_freqtrade/<name>_<timerange>.txt and
# orders/<name>_<timerange>.csv.gz. Resumable: finished runs are skipped.
cd "$(dirname "$0")/../../.." || exit 1
here=user_data/candidates/round11
names=${*:-"gate_a90_20 gate_a90_20_supply always_on_20"}
mkdir -p "$here/results_freqtrade" "$here/orders" "$here/exports"
for name in $names; do
  for tr in ${TIMERANGES:-20190101-20201231 20210101-20231231 20240101-20260630}; do
    [ -f "$here/orders/${name}_$tr.csv.gz" ] && continue
    exp=$here/exports/${name}_$tr
    rm -rf "$exp" && mkdir -p "$exp"
    OMP_NUM_THREADS=2 nice -n 19 .env/bin/freqtrade backtesting -c "$here/configs/$name.json" \
      --datadir user_data/data_bed/round11_ft --timerange "$tr" --strategy-path user_data/strategies \
      --export trades --backtest-directory "$exp" --breakdown year --logfile "$exp/freqtrade.log" 2>/dev/null \
      | grep -vE '^[0-9]{4}-[0-9]{2}-[0-9]{2} ' | sed 's/[[:space:]]*$//' > "$here/results_freqtrade/${name}_$tr.txt"
    nice -n 19 .env/bin/python user_data/candidates/round6/export_orders.py "$exp" "$here/orders/${name}_$tr.csv.gz"
    echo "done $name $tr $(date +%T)"
  done
done
