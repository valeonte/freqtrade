# Daily account report

An HTML email with the Binance spot account's performance: returns over 1D, 1W, 1M, WTD,
MTD and YTD for the account, BTC and ETH; charts of the last 30 days and 12 months
rebased to 100; current holdings; and last week's trades (or the last five, if more).

Values are in USD (USDT and other dollar stablecoins count as $1) at the 00:00 UTC daily
close. Account returns are time-weighted, so deposits and withdrawals are not gains.

## How it works

The history is rebuilt from Binance, not from freqtrade: today's balances, walked back
through every trade (`myTrades`), deposit, withdrawal, dust conversion and Convert
trade, give the holdings at each daily close, which are valued with daily candles.
Records are cached in `~/.local/state/account-report/`, so after the first run (which
looks for trades in every symbol quoted in a currency the account has used, a few
minutes) a daily run only fetches what is new. Each real run is checked against
Binance's own daily snapshots of the last month, and the email says if they disagree.

Not covered: Simple Earn, the Funding wallet, futures and delisted symbols. A coin
that is missing shows up as a note at the bottom of the email.

## Run

Python + matplotlib only, in a throwaway pixi environment (`run_report.sh`):

```bash
tools/report/run_report.sh --mock --out /tmp/report   # sample from a made-up account, no key
tools/report/run_report.sh --out /tmp/report          # real account, files only
tools/report/run_report.sh --send                     # real account, emailed
```

Settings come from the environment or any `*.env` file in `~/.config/account-report/`
(`KEY=value` lines, never committed; `chmod 600` them):

| Key | |
| --- | --- |
| `FREQTRADE__EXCHANGE__KEY`, `FREQTRADE__EXCHANGE__SECRET` | Binance key; read-only is enough |
| `SMTP_USER`, `SMTP_PASSWORD` | e.g. a Gmail address and an app password |
| `SMTP_HOST`, `SMTP_PORT` | default `smtp.gmail.com`, `465` |
| `REPORT_TO` | recipient, default `SMTP_USER` |
| `REPORT_ASSETS` | extra coins to look for trades in, comma-separated |

Cron (06:00 London; the machine's clock is on Europe/London, Ubuntu's cron ignores `CRON_TZ`):

```
0 6 * * * /home/fistix/repos/freqtrade/tools/report/run_report.sh --send >> /home/fistix/.local/state/account-report/cron.log 2>&1
```

Tests: `.env/bin/python -m pytest tools/report/tests`.
