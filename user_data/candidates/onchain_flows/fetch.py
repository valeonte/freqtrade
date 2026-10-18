"""
Pull every ERC-20 Transfer into Binance's hot wallets from the owner's Erigon archive node.

Binance sweeps each user's deposit address into a handful of hot wallets; Binance 14 takes ~98% of
the sweeps since 2023 (checked on 2,000-block samples in 2023-11, 2024-03, 2024-10 and 2025-08), so a
transfer into one of these wallets is, to within the sweep delay, a user deposit. Transfers whose
sender is another Binance wallet are internal and dropped later, in research.py.

Node address: user_data/onchain_node.json (gitignored), {"rpc_url": "http://<ip>:8545"}.
Output (gitignored): user_data/data_bed/onchain/transfers/<first block>.parquet, one file per
10,000 blocks, resumable.

    nice -n 19 .env/bin/python user_data/candidates/onchain_flows/fetch.py [--from 18470000] [--to N] \
        [--workers 6] [--withdrawals]

--withdrawals pulls transfers out of the wallets that pay withdrawals into
user_data/data_bed/onchain/withdrawals/ instead.
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests


URL = json.loads(Path("user_data/onchain_node.json").read_text())["rpc_url"]
BED = Path(os.environ.get("FT_DATA_BED", "user_data/data_bed"))  # a worktree points this at the main checkout
OUT = BED / "onchain" / "transfers"  # deposits: sender -> Binance wallet
OUT_W = BED / "onchain" / "withdrawals"  # withdrawals: Binance wallet -> recipient
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
CHUNK = 10_000
STEP = 2_000  # blocks per eth_getLogs call

# Etherscan labels
HOT = {
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance 16",
    "0xf977814e90da44bfa03b6295a0616a897441acec": "Binance 8",
}
# other Binance wallets, only used to drop internal transfers
OTHER = {
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": "Binance 17",
    "0x9696f59e4d72e237be84ffd425dcad154bf96976": "Binance 18",
    "0x4976a4a02f38326660d17bf34b431dc6e2eb2327": "Binance 20",
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": "Binance 1",
    "0xd551234ae421e3bcba99a0da6d736074f22192ff": "Binance 2",
    "0x564286362092d8e7936f0549571a803b203aaced": "Binance 3",
    "0x0681d8db095565fe8a346fa0277bffde9c0edbbf": "Binance 4",
    "0xfe9e8709d3215310075d67e3ed32a380ccf451c8": "Binance 5",
    "0x4e9ce36e442e55ecd9025b9a6e0d88485d628a67": "Binance 6",
    "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": "Binance 7",
    "0x5a52e96bacdabb82fd05763e25335261b270efcb": "Binance 28",
}
BINANCE = HOT | OTHER
# wallets that pay out withdrawals (2,000-block samples in 2024-03, 2025-08, 2026-09)
PAYOUT = [w for w, n in BINANCE.items() if n.split()[1] in ("14", "15", "16", "17", "18", "20")]

_session = requests.Session()


def rpc(method: str, params: list):
    for attempt in range(6):
        try:
            r = _session.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=600)
            r.raise_for_status()
            out = r.json()
            if "error" in out:
                raise RuntimeError(out["error"])
            return out["result"]
        except (requests.RequestException, RuntimeError):
            if attempt == 5:
                raise
            time.sleep(2**attempt)


def _topic(addr: str) -> str:
    return "0x" + addr[2:].rjust(64, "0")


def fetch_chunk(start: int, withdrawals: bool = False) -> int:
    path = (OUT_W if withdrawals else OUT) / f"{start}.parquet"
    if withdrawals:
        topics = [TRANSFER, [_topic(w) for w in PAYOUT], None]
    else:
        topics = [TRANSFER, None, [_topic(w) for w in HOT]]
    if path.exists():
        return -1
    rows = []
    for a in range(start, start + CHUNK, STEP):
        logs = rpc(
            "eth_getLogs",
            [{"fromBlock": hex(a), "toBlock": hex(a + STEP - 1), "topics": topics}],
        )
        for lg in logs:
            if len(lg["topics"]) != 3 or len(lg["data"]) < 66:  # ERC-721 puts the id in a topic
                continue
            rows.append(
                (
                    int(lg["blockNumber"], 16),
                    int(lg["blockTimestamp"], 16),
                    int(lg["logIndex"], 16),
                    lg["address"].lower(),
                    "0x" + lg["topics"][1][-40:],
                    "0x" + lg["topics"][2][-40:],
                    float(int(lg["data"][2:66], 16)),  # raw units; decimals applied later
                )
            )
    cols = ["wallet", "recipient"] if withdrawals else ["sender", "wallet"]
    df = pd.DataFrame(rows, columns=["block", "ts", "log_index", "token", *cols, "raw"])
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.rename(path)
    return len(df)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", type=int, default=18_470_000)  # 2023-10-31
    p.add_argument("--to", type=int, default=None)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--withdrawals", action="store_true", help="transfers out of Binance's payout wallets instead")
    a = p.parse_args()
    end = a.to or int(rpc("eth_blockNumber", []), 16) - 64
    (OUT_W if a.withdrawals else OUT).mkdir(parents=True, exist_ok=True)
    starts = list(range(a.start - a.start % CHUNK, end - CHUNK + 1, CHUNK))
    t0, done = time.time(), 0
    with ThreadPoolExecutor(a.workers) as ex:
        for i, n in enumerate(ex.map(lambda s: fetch_chunk(s, a.withdrawals), starts)):
            done += n >= 0
            if i % 20 == 0:
                print(f"{i + 1}/{len(starts)} chunks, {time.time() - t0:.0f}s", flush=True)
    print(f"done: {len(starts)} chunks to block {starts[-1] + CHUNK - 1}", flush=True)


if __name__ == "__main__":
    main()
