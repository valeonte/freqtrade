#!/bin/bash
# Study 24: freqtrade backtests of the live bot, alone and holding FOMC / CPI days while flat.
cd "$(dirname "$0")/../../.." || exit 1
out=user_data/candidates/positioning/results_24_freqtrade
mkdir -p "$out"
for tr in 20190101-20260630 20190101-20201231 20210101-20231231 20240101-20260630; do
  for v in live fomc cpi; do
    nice -n 19 .env/bin/freqtrade backtesting -c user_data/candidates/positioning/config_24_$v.json \
      --datadir user_data/data_bed/binance --timerange $tr --strategy-path user_data/strategies \
      --export none --breakdown year 2>/dev/null > "$out/${v}_$tr.txt"
    echo "done $v $tr"
  done
done
