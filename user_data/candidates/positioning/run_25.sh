#!/bin/bash
# Study 25: freqtrade backtests of the fast exit (SMA50 out, new 20-day high back in).
cd "$(dirname "$0")/../../.." || exit 1
out=user_data/candidates/positioning/results_25_freqtrade
mkdir -p "$out"
for tr in 20190101-20260630 20190101-20201231 20210101-20231231 20240101-20260630; do
  nice -n 19 .env/bin/freqtrade backtesting -c user_data/candidates/positioning/config_25_fast.json \
    --datadir user_data/data_bed/binance --timerange $tr --strategy-path user_data/strategies \
    --export none --breakdown year 2>/dev/null | grep -vE '^[0-9]{4}-[0-9]{2}-[0-9]{2} ' > "$out/fast_$tr.txt"
  echo "done $tr"
done
