"""
Name the tokens in the pulled deposits and match them to Binance USDT pairs.

For every token contract with deposits from at least 50 distinct senders (spam airdrops come from
one sender, real deposits from many deposit addresses), read symbol() and decimals() from the node.
A contract maps to the Binance pair whose base equals its symbol (case-insensitive). Where several
contracts share a symbol (fakes, old versions), the one with the most distinct senders wins.
Stablecoins are kept under their own symbol and valued at $1.

Output (gitignored): user_data/data_bed/onchain/tokens.parquet

    .env/bin/python user_data/candidates/onchain_flows/tokens.py
"""

import json
from pathlib import Path

import pandas as pd
from fetch import BED, OUT, rpc


STABLES = {"USDT", "USDC", "FDUSD", "DAI", "TUSD", "BUSD", "USDP", "PYUSD", "USDE", "USD1", "RLUSD", "USDS"}
MIN_SENDERS = 50


def _call(token: str, selector: str) -> str | None:
    try:
        return rpc("eth_call", [{"to": token, "data": selector}, "latest"])
    except RuntimeError:
        return None


def _text(hexdata: str | None) -> str | None:
    if not hexdata or hexdata == "0x":
        return None
    b = bytes.fromhex(hexdata[2:])
    if len(b) >= 96:  # ABI string: offset, length, bytes
        n = int.from_bytes(b[32:64], "big")
        s = b[64 : 64 + n]
    else:  # bytes32 (MKR, SAI)
        s = b[:32].rstrip(b"\0")
    try:
        return s.decode("utf-8").strip() or None
    except UnicodeDecodeError:
        return None


def main():
    df = pd.concat(pd.read_parquet(p, columns=["token", "sender"]) for p in sorted(OUT.glob("*.parquet")))
    senders = df.groupby("token")["sender"].nunique()
    cand = senders[senders >= MIN_SENDERS].sort_values(ascending=False)
    print(f"{len(senders)} contracts, {len(cand)} with >= {MIN_SENDERS} senders")
    pairs = {p.split("/")[0].upper() for p in json.loads(Path("user_data/honest_bed/candidate_pairs.json").read_text())}
    rows = []
    for token, n in cand.items():
        sym = _text(_call(token, "0x95d89b41"))
        dec = _call(token, "0x313ce567")
        dec = int(dec, 16) if dec and dec != "0x" else None
        rows.append((token, sym, dec, int(n)))
    meta = pd.DataFrame(rows, columns=["token", "symbol", "decimals", "senders"]).dropna()
    meta["symbol"] = meta["symbol"].str.upper()
    meta["stable"] = meta["symbol"].isin(STABLES)
    meta["listed"] = meta["symbol"].isin(pairs)
    meta = meta[meta["stable"] | meta["listed"]]
    meta = meta.sort_values("senders", ascending=False).drop_duplicates("symbol")
    meta.to_parquet(BED / "onchain" / "tokens.parquet", index=False)
    print(f"{len(meta)} tokens kept ({meta['stable'].sum()} stablecoins)")
    print(meta.head(40).to_string(index=False))


if __name__ == "__main__":
    main()
