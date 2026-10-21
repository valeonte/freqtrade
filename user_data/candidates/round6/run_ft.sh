#!/bin/bash
# Round 6 freqtrade backtests with every order exported: run_ft.sh [config names...]
# Output: results_freqtrade/<name>_<timerange>.txt (the usual report) and orders/<name>_<timerange>.csv.gz
cd "$(dirname "$0")/../../.." || exit 1
here=user_data/candidates/round6
names=${*:-"tranches tranches_noresize daily daily_noresize daily_cadence weekly weekly_noresize monthly monthly_noresize
  trend_only weekly_tue weekly_wed weekly_thu weekly_fri weekly_sat weekly_sun monthly_08 monthly_15 monthly_22"}
mkdir -p "$here/results_freqtrade" "$here/orders"
for name in $names; do
  for tr in 20190101-20260630 20190101-20201231 20210101-20231231 20240101-20260630; do
    exp=$here/exports/${name}_$tr
    rm -rf "$exp" && mkdir -p "$exp"
    nice -n 19 .env/bin/freqtrade backtesting -c "$here/configs/$name.json" \
      --datadir user_data/data_bed/binance --timerange "$tr" --strategy-path user_data/strategies \
      --export trades --backtest-directory "$exp" --breakdown year 2>/dev/null \
      | grep -vE '^[0-9]{4}-[0-9]{2}-[0-9]{2} ' | sed 's/[[:space:]]*$//' > "$here/results_freqtrade/${name}_$tr.txt"
    nice -n 19 .env/bin/python "$here/export_orders.py" "$exp" "$here/orders/${name}_$tr.csv.gz"
  done
done
