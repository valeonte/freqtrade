#!/bin/bash
# Study 21: freqtrade backtests of the live bot with a 0/10/20% low-vol alt sleeve, one at a time.
cd "$(dirname "$0")/../../.." || exit 1
out=user_data/candidates/alt_sleeve/results
mkdir -p "$out"
for tr in 20190101-20260630 20190101-20201231 20210101-20231231 20240101-20260630; do
  for s in 0 10 20; do
    nice -n 19 .env/bin/freqtrade backtesting -c user_data/candidates/alt_sleeve/config_sleeve$s.json \
      --datadir user_data/data_bed/binance --timerange $tr --strategy-path user_data/strategies \
      --export none --breakdown year > "$out/sleeve${s}_$tr.txt" 2>/dev/null
    echo "done sleeve $s $tr"
  done
done
