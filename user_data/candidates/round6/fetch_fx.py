"""
Fetch the daily GBP-per-USD rate for round 6 into user_data/data_bed/external/fx/gbp_per_usd.csv.

Source: the ECB's euro foreign exchange reference rates (daily since 1999, published around 16:00
CET on TARGET business days), crossed as GBP per EUR over USD per EUR. HMRC asks for a reasonable
method used consistently to value tokens in sterling; a published daily reference rate is that.
USDT is taken at 1 USD. Output rows: date (UTC midnight), gbp_per_usd; days without a fixing are
left out and forward-filled by the reader.

    nice -n 19 .env/bin/python user_data/candidates/round6/fetch_fx.py
"""

import io
import time
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd


OUT = Path("user_data/data_bed/external/fx")
URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
    for i in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310
                return r.read()
        except Exception:
            time.sleep(2**i)
    raise RuntimeError(url)


def gbp_per_usd() -> pd.Series:
    with zipfile.ZipFile(io.BytesIO(get(URL))) as zf:
        df = pd.read_csv(zf.open(zf.namelist()[0]), usecols=["Date", "USD", "GBP"], na_values="N/A")
    df = df.dropna()
    s = (df["GBP"] / df["USD"]).set_axis(pd.to_datetime(df["Date"], utc=True)).sort_index()
    return s.rename("gbp_per_usd")


def load(path: Path = OUT / "gbp_per_usd.csv") -> pd.Series:
    s = pd.read_csv(path, index_col=0, parse_dates=[0])["gbp_per_usd"]
    s.index = pd.to_datetime(s.index, utc=True)
    return s


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    s = gbp_per_usd()
    s.to_csv(OUT / "gbp_per_usd.csv", index_label="date")
    print(len(s), s.index[0].date(), s.index[-1].date(), s[s.index >= "2019-01-01"].describe().round(4).to_dict())
