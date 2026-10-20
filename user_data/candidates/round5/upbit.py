"""
Upbit trade notices -> events (studies 33 and 36). Keyword lists were written from the notice titles
alone (2017-10 -> 2026-10), before any price was looked at.

Title forms by era: "스팀달러(SBD), 블록틱스(TIX) 상장 안내" (2017), "원화 마켓 신규 상장 (스톰 STORM)" /
"BTC 마켓 코인 추가 (비트튜브 TUBE)" (2018-20), "원화 마켓 디지털 자산 추가 (휴먼스케이프 HUM)" /
"KRW, BTC 마켓 디지털 자산 추가 (APT)" (2020-24), "웜홀(W) 신규 거래지원 안내 (KRW, BTC, USDT 마켓)" /
"레이디움(RAY) KRW, USDT 마켓 디지털 자산 추가" (2024 ->). Upbit appends later edits to the title
("(거래지원 개시 시점 연기 안내)", "(완료)", "(업데이트)"); `first_listed_at` is the original publication.
"""

import json
import re

import pandas as pd
from common import EXT


LISTING = ("신규 거래지원", "디지털 자산 추가", "코인 추가", "신규 상장", "상장 안내", "상장", "마켓 오픈", "거래 오픈")
NOT_LISTING = ("종료", "유의", "중단", "철회", "사기", "재개", "청산")
WARN_LIFT = "해제"
NOT_WARN_LIFT = ("종료",)  # lifts announced together with a delisting
MARKET_WORDS = {"KRW", "BTC", "USDT", "ETH"}


def load(path: str = "upbit/notices.json") -> pd.DataFrame:
    d = pd.DataFrame(json.loads((EXT / path).read_text()))
    d["T"] = pd.to_datetime(d["first_listed_at"], utc=True)
    return d.sort_values("T").reset_index(drop=True)


def tickers(title: str) -> list[str]:
    """Coin tickers in a title: upper-case tokens inside parentheses ("(SBD)", "(스톰 STORM)", "(CTC, LPT)",
    "(ETH/KRW)"), skipping the market list ("(KRW, BTC, USDT 마켓)") and edit remarks."""
    out = []
    for grp in re.findall(r"\(([^()]*)\)", title):
        if "마켓" in grp:
            continue
        for tok in re.findall(r"[A-Za-z0-9]+(?:/KRW|/BTC|/USDT)?", grp):
            base = tok.split("/")[0]
            if not re.search(r"[A-Z]", base) or not base.upper() == base:
                continue
            if "/" not in tok and base in MARKET_WORDS and len(re.findall(r"[A-Z0-9]+", grp)) > 1 and "," in grp:
                continue
            out.append(base)
    seen = []
    for t in out:
        if t not in seen:
            seen.append(t)
    return seen


def markets(title: str) -> set[str]:
    m = set()
    if "KRW" in title or "원화" in title:
        m.add("KRW")
    for w in ("BTC", "USDT"):
        if re.search(rf"\b{w}\b[^)]*마켓|{w} 마켓|{w}, |, {w}", title):
            m.add(w)
    return m


def listings(d: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (notice, coin) for notices that add a coin to an Upbit market."""
    d = load() if d is None else d
    rows = []
    seen_coins: set[str] = set()
    for _, n in d.iterrows():
        t = n["title"]
        core = re.sub(r"\((?:[^()]*(?:안내|완료|업데이트|재안내|변경|연기))\)\s*$", "", t)
        if not any(k in core for k in LISTING) or any(k in core for k in NOT_LISTING):
            continue
        mk = markets(core)
        # per-coin market lists, e.g. "셀레스티아(TIA)(KRW, BTC, USDT 마켓), 아이오넷(IO)(BTC, USDT 마켓)"
        per_coin = {c: markets(m) for c, m in re.findall(r"\(([A-Z0-9]+)\)\s*\(([^()]*마켓)\)", core)}
        for c in tickers(core):
            rows.append(
                {
                    "T": n["T"],
                    "id": n["id"],
                    "title": t,
                    "coin": c,
                    "krw": "KRW" in per_coin.get(c, mk),
                    "market_stated": bool(mk),
                    "new_to_upbit": c not in seen_coins,
                }
            )
        seen_coins.update(tickers(core))
    out = pd.DataFrame(rows)
    out["n_in_notice"] = out.groupby("id")["coin"].transform("size")
    return out


def warning_lifts(d: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per (notice, coin) lifting an investment-warning designation (유의 종목 ... 해제)."""
    d = load() if d is None else d
    rows = []
    for _, n in d.iterrows():
        t = n["title"]
        if "유의" not in t or WARN_LIFT not in t or any(k in t for k in NOT_WARN_LIFT):
            continue
        cs = tickers(t)
        if not cs:  # 2019-20 form: "TT, LSK 유의 종목 해제 안내"
            head = t.split("유의")[0]
            cs = [c for c in re.findall(r"[A-Z0-9]{2,}", head) if c not in MARKET_WORDS]
        for c in cs:
            rows.append({"T": n["T"], "id": n["id"], "title": t, "coin": c})
    out = pd.DataFrame(rows)
    out["n_in_notice"] = out.groupby("id")["coin"].transform("size")
    return out
