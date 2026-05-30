"""
chatbot_price_fetcher.py  — Twelve Data primary, NSE fallback
──────────────────────────────────────────────────────────────
Data source hierarchy:
  1. Twelve Data API  — primary, works globally from any server,
                        800 free credits/day, NSE supported
  2. NSE India API    — fallback (works when running on Indian IP)
  3. Smart cache      — 5 min during market hours, 6 hours after close
                        dramatically reduces API calls at scale

Setup:
  Add TWELVE_DATA_API_KEY=your_key to backend/.env
  Get free key at: https://twelvedata.com (free tier, no card needed)
"""

import os
import requests
import pandas as pd
import threading
import time
import random
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
TWELVE_BASE     = "https://api.twelvedata.com"

# ─────────────────────────────────────────────────────────────
# Smart Cache — reduces API calls by 95%+ at scale
# ─────────────────────────────────────────────────────────────

class _Cache:
    def __init__(self, market_ttl=300, closed_ttl=21600):
        self._data       = {}
        self._lock       = threading.Lock()
        self.market_ttl  = market_ttl   # 5 min during market hours
        self.closed_ttl  = closed_ttl   # 6 hours after close

    def _ttl(self) -> int:
        now = datetime.now()
        if now.weekday() >= 5:
            return self.closed_ttl
        h, m = now.hour, now.minute
        is_open = (h > 9 or (h == 9 and m >= 15)) and \
                  (h < 15 or (h == 15 and m <= 30))
        return self.market_ttl if is_open else self.closed_ttl

    def get(self, key: str):
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            data, ts = entry
            if time.time() - ts > self._ttl():
                del self._data[key]
                return None
            return data

    def get_stale(self, key: str):
        """Return expired cache as last resort."""
        with self._lock:
            entry = self._data.get(key)
            return entry[0] if entry else None

    def set(self, key: str, data):
        with self._lock:
            self._data[key] = (data, time.time())


_price_cache = _Cache(market_ttl=300,   closed_ttl=21600)
_ohlcv_cache = _Cache(market_ttl=3600,  closed_ttl=21600)  # OHLCV: 1hr cache


# ─────────────────────────────────────────────────────────────
# Holiday detection
# ─────────────────────────────────────────────────────────────

NSE_HOLIDAYS = {
    date(2025,1,26), date(2025,2,26), date(2025,3,14),
    date(2025,3,31), date(2025,4,10), date(2025,4,14),
    date(2025,4,18), date(2025,5,1),  date(2025,8,15),
    date(2025,8,27), date(2025,10,2), date(2025,10,20),
    date(2025,10,21),date(2025,10,24),date(2025,11,5),
    date(2025,12,25),
    date(2026,1,26), date(2026,2,19), date(2026,3,28),
    date(2026,3,30), date(2026,4,2),  date(2026,4,10),
    date(2026,4,14), date(2026,5,1),  date(2026,8,15),
    date(2026,8,27), date(2026,10,2), date(2026,10,20),
    date(2026,10,21),date(2026,11,5), date(2026,11,25),
    date(2026,12,25),
}


def _last_trading_day(from_date: date) -> date:
    d = from_date
    for _ in range(14):
        if d.weekday() < 5 and d not in NSE_HOLIDAYS:
            return d
        d -= timedelta(days=1)
    return from_date


def is_market_open() -> dict:
    today   = date.today()
    now     = datetime.now()
    weekday = today.weekday()

    if weekday >= 5:
        return {"is_open": False, "reason": "weekend",
                "as_of_date": _last_trading_day(today - timedelta(days=1))}
    if today in NSE_HOLIDAYS:
        return {"is_open": False, "reason": "holiday",
                "as_of_date": _last_trading_day(today - timedelta(days=1))}

    open_t  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    close_t = now.replace(hour=15, minute=30, second=0, microsecond=0)

    if now < open_t:
        return {"is_open": False, "reason": "pre_market",
                "as_of_date": _last_trading_day(today - timedelta(days=1))}
    if now > close_t:
        return {"is_open": False, "reason": "after_hours", "as_of_date": today}
    return {"is_open": True, "reason": "live", "as_of_date": today}


# ─────────────────────────────────────────────────────────────
# Ticker resolver
# ─────────────────────────────────────────────────────────────

# Maps user input → (nse_symbol, twelvedata_symbol)
# Twelve Data format for NSE: "RELIANCE:NSE"
_ALIASES: dict[str, tuple[str, str]] = {
    "RELIANCE":    ("RELIANCE",   "RELIANCE:NSE"),
    "RIL":         ("RELIANCE",   "RELIANCE:NSE"),
    "TCS":         ("TCS",        "TCS:NSE"),
    "INFY":        ("INFY",       "INFY:NSE"),
    "INFOSYS":     ("INFY",       "INFY:NSE"),
    "WIPRO":       ("WIPRO",      "WIPRO:NSE"),
    "HCLTECH":     ("HCLTECH",    "HCLTECH:NSE"),
    "HCL":         ("HCLTECH",    "HCLTECH:NSE"),
    "TECHM":       ("TECHM",      "TECHM:NSE"),
    "TECHMAHINDRA":("TECHM",      "TECHM:NSE"),
    "HDFCBANK":    ("HDFCBANK",   "HDFCBANK:NSE"),
    "HDFC":        ("HDFCBANK",   "HDFCBANK:NSE"),
    "ICICIBANK":   ("ICICIBANK",  "ICICIBANK:NSE"),
    "ICICI":       ("ICICIBANK",  "ICICIBANK:NSE"),
    "SBIN":        ("SBIN",       "SBIN:NSE"),
    "SBI":         ("SBIN",       "SBIN:NSE"),
    "KOTAKBANK":   ("KOTAKBANK",  "KOTAKBANK:NSE"),
    "KOTAK":       ("KOTAKBANK",  "KOTAKBANK:NSE"),
    "AXISBANK":    ("AXISBANK",   "AXISBANK:NSE"),
    "AXIS":        ("AXISBANK",   "AXISBANK:NSE"),
    "INDUSINDBK":  ("INDUSINDBK", "INDUSINDBK:NSE"),
    "INDUSIND":    ("INDUSINDBK", "INDUSINDBK:NSE"),
    "FEDERALBNK":  ("FEDERALBNK", "FEDERALBNK:NSE"),
    "IDFCFIRSTB":  ("IDFCFIRSTB", "IDFCFIRSTB:NSE"),
    "IDFC":        ("IDFCFIRSTB", "IDFCFIRSTB:NSE"),
    "TATAMOTORS":  ("TATAMOTORS", "TATAMOTORS:NSE"),
    "TATAMOTOR":   ("TATAMOTORS", "TATAMOTORS:NSE"),
    "TATASTEEL":   ("TATASTEEL",  "TATASTEEL:NSE"),
    "TATAPOWER":   ("TATAPOWER",  "TATAPOWER:NSE"),
    "TATACONSUM":  ("TATACONSUM", "TATACONSUM:NSE"),
    "TATACONSUMER":("TATACONSUM", "TATACONSUM:NSE"),
    "MARUTI":      ("MARUTI",     "MARUTI:NSE"),
    "BAJFINANCE":  ("BAJFINANCE", "BAJFINANCE:NSE"),
    "BAJAJFIN":    ("BAJFINANCE", "BAJFINANCE:NSE"),
    "BAJAJFINSV":  ("BAJAJFINSV", "BAJAJFINSV:NSE"),
    "BAJAJFINSERV":("BAJAJFINSV", "BAJAJFINSV:NSE"),
    "BAJAJAUTO":   ("BAJAJ-AUTO", "BAJAJ-AUTO:NSE"),
    "BAJAJ-AUTO":  ("BAJAJ-AUTO", "BAJAJ-AUTO:NSE"),
    "HEROMOTOCO":  ("HEROMOTOCO", "HEROMOTOCO:NSE"),
    "HERO":        ("HEROMOTOCO", "HEROMOTOCO:NSE"),
    "EICHERMOT":   ("EICHERMOT",  "EICHERMOT:NSE"),
    "EICHER":      ("EICHERMOT",  "EICHERMOT:NSE"),
    "SUNPHARMA":   ("SUNPHARMA",  "SUNPHARMA:NSE"),
    "SUN":         ("SUNPHARMA",  "SUNPHARMA:NSE"),
    "DRREDDY":     ("DRREDDY",    "DRREDDY:NSE"),
    "DRREDDYS":    ("DRREDDY",    "DRREDDY:NSE"),
    "CIPLA":       ("CIPLA",      "CIPLA:NSE"),
    "DIVISLAB":    ("DIVISLAB",   "DIVISLAB:NSE"),
    "DIVIS":       ("DIVISLAB",   "DIVISLAB:NSE"),
    "ASIANPAINT":  ("ASIANPAINT", "ASIANPAINT:NSE"),
    "ASIAN":       ("ASIANPAINT", "ASIANPAINT:NSE"),
    "ULTRACEMCO":  ("ULTRACEMCO", "ULTRACEMCO:NSE"),
    "ULTRATECH":   ("ULTRACEMCO", "ULTRACEMCO:NSE"),
    "TITAN":       ("TITAN",      "TITAN:NSE"),
    "NESTLEIND":   ("NESTLEIND",  "NESTLEIND:NSE"),
    "NESTLE":      ("NESTLEIND",  "NESTLEIND:NSE"),
    "BRITANNIA":   ("BRITANNIA",  "BRITANNIA:NSE"),
    "HINDALCO":    ("HINDALCO",   "HINDALCO:NSE"),
    "ONGC":        ("ONGC",       "ONGC:NSE"),
    "NTPC":        ("NTPC",       "NTPC:NSE"),
    "POWERGRID":   ("POWERGRID",  "POWERGRID:NSE"),
    "ADANIPORTS":  ("ADANIPORTS", "ADANIPORTS:NSE"),
    "ADANI":       ("ADANIPORTS", "ADANIPORTS:NSE"),
    "ADANIGREEN":  ("ADANIGREEN", "ADANIGREEN:NSE"),
    "ADANIENT":    ("ADANIENT",   "ADANIENT:NSE"),
    "BHARTIARTL":  ("BHARTIARTL", "BHARTIARTL:NSE"),
    "AIRTEL":      ("BHARTIARTL", "BHARTIARTL:NSE"),
    "ZOMATO":      ("ZOMATO",     "ZOMATO:NSE"),
    "IRCTC":       ("IRCTC",      "IRCTC:NSE"),
    "DMART":       ("DMART",      "DMART:NSE"),
    "AVENUESUPER": ("DMART",      "DMART:NSE"),
    "NYKAA":       ("NYKAA",      "NYKAA:NSE"),
    "FSNNEC":      ("NYKAA",      "NYKAA:NSE"),
    "PAYTM":       ("PAYTM",      "PAYTM:NSE"),
    "POLICYBZR":   ("POLICYBZR",  "POLICYBZR:NSE"),
    "POLICYBAZAAR":("POLICYBZR",  "POLICYBZR:NSE"),
    "NAUKRI":      ("NAUKRI",     "NAUKRI:NSE"),
    "INFOEDGE":    ("NAUKRI",     "NAUKRI:NSE"),
    "PIDILITIND":  ("PIDILITIND", "PIDILITIND:NSE"),
    "PIDILITE":    ("PIDILITIND", "PIDILITIND:NSE"),
    "HAVELLS":     ("HAVELLS",    "HAVELLS:NSE"),
    "SIEMENS":     ("SIEMENS",    "SIEMENS:NSE"),
    "ABB":         ("ABB",        "ABB:NSE"),
    "COLPAL":      ("COLPAL",     "COLPAL:NSE"),
    "COLGATE":     ("COLPAL",     "COLPAL:NSE"),
    "BERGEPAINT":  ("BERGEPAINT", "BERGEPAINT:NSE"),
    "BERGER":      ("BERGEPAINT", "BERGEPAINT:NSE"),
    "JSWSTEEL":    ("JSWSTEEL",   "JSWSTEEL:NSE"),
    "JSW":         ("JSWSTEEL",   "JSWSTEEL:NSE"),
    "LTIM":        ("LTIM",       "LTIM:NSE"),
    "LTIMINDTREE": ("LTIM",       "LTIM:NSE"),
    "LTI":         ("LTIM",       "LTIM:NSE"),
    "APOLLOHOSP":  ("APOLLOHOSP", "APOLLOHOSP:NSE"),
    "APOLLO":      ("APOLLOHOSP", "APOLLOHOSP:NSE"),
    "MUTHOOTFIN":  ("MUTHOOTFIN", "MUTHOOTFIN:NSE"),
    "MUTHOOT":     ("MUTHOOTFIN", "MUTHOOTFIN:NSE"),
    "COALINDIA":   ("COALINDIA",  "COALINDIA:NSE"),
    "GRASIM":      ("GRASIM",     "GRASIM:NSE"),
    "TRENT":       ("TRENT",      "TRENT:NSE"),
    "DIXON":       ("DIXON",      "DIXON:NSE"),
    "POLYCAB":     ("POLYCAB",    "POLYCAB:NSE"),
    "KEI":         ("KEI",        "KEI:NSE"),
    "SUZLON":      ("SUZLON",     "SUZLON:NSE"),
    "WAAREEENER":  ("WAAREEENER", "WAAREEENER:NSE"),
    "WAAREE":      ("WAAREEENER", "WAAREEENER:NSE"),
    "KALYANKJIL":  ("KALYANKJIL", "KALYANKJIL:NSE"),
    "KALYAN":      ("KALYANKJIL", "KALYANKJIL:NSE"),
    "GAIL":        ("GAIL",       "GAIL:NSE"),
    "ITC":         ("ITC",        "ITC:NSE"),
    "LT":          ("LT",         "LT:NSE"),
    "PERSISTENT":  ("PERSISTENT", "PERSISTENT:NSE"),
    "COFORGE":     ("COFORGE",    "COFORGE:NSE"),
    "MPHASIS":     ("MPHASIS",    "MPHASIS:NSE"),
    "HDFCLIFE":    ("HDFCLIFE",   "HDFCLIFE:NSE"),
    "SBILIFE":     ("SBILIFE",    "SBILIFE:NSE"),
    "ICICIGI":     ("ICICIGI",    "ICICIGI:NSE"),
    "CHOLAFIN":    ("CHOLAFIN",   "CHOLAFIN:NSE"),
    "DLF":         ("DLF",        "DLF:NSE"),
    "GODREJPROP":  ("GODREJPROP", "GODREJPROP:NSE"),
    "OBEROIRLTY":  ("OBEROIRLTY", "OBEROIRLTY:NSE"),
    "PRESTIGE":    ("PRESTIGE",   "PRESTIGE:NSE"),
    "CANBK":       ("CANBK",      "CANBK:NSE"),
    "BANKBARODA":  ("BANKBARODA", "BANKBARODA:NSE"),
    "PNB":         ("PNB",        "PNB:NSE"),
    "NHPC":        ("NHPC",       "NHPC:NSE"),
    "JSWENERGY":   ("JSWENERGY",  "JSWENERGY:NSE"),
    "TORNTPOWER":  ("TORNTPOWER", "TORNTPOWER:NSE"),
    "MOTHERSUMI":  ("MOTHERSUMI", "MOTHERSUMI:NSE"),
    "MOTHERSON":   ("MOTHERSUMI", "MOTHERSUMI:NSE"),
}


def resolve_ticker(symbol: str) -> tuple[str, str]:
    """
    Returns (nse_symbol, twelvedata_symbol).
    e.g. 'reliance' → ('RELIANCE', 'RELIANCE:NSE')
         'TCS.NS'   → ('TCS',      'TCS:NSE')
    """
    s = symbol.strip().upper().replace(" ","").replace(".","").replace("-","")

    # Handle .NS suffix
    if symbol.strip().upper().endswith(".NS"):
        nse = symbol.strip().upper().replace(".NS","")
        return nse, f"{nse}:NSE"

    if s in _ALIASES:
        return _ALIASES[s]

    # Default: treat as NSE symbol
    return s, f"{s}:NSE"


# ─────────────────────────────────────────────────────────────
# Twelve Data — primary data source
# ─────────────────────────────────────────────────────────────

def _td_request(endpoint: str, params: dict) -> dict | None:
    """Makes a Twelve Data API request. Returns dict or None on failure."""
    if not TWELVE_DATA_KEY:
        print("[price] TWELVE_DATA_API_KEY not set in .env")
        return None
    try:
        params["apikey"] = TWELVE_DATA_KEY
        r = requests.get(
            f"{TWELVE_BASE}/{endpoint}",
            params=params,
            timeout=12,
        )
        if r.status_code != 200:
            print(f"[price] Twelve Data HTTP {r.status_code}: {r.text[:100]}")
            return None
        data = r.json()
        # Check for API-level errors
        if data.get("status") == "error" or "code" in data:
            print(f"[price] Twelve Data error: {data.get('message','')}")
            return None
        return data
    except Exception as e:
        print(f"[price] Twelve Data request failed: {e}")
        return None


def _td_quote(td_symbol: str) -> dict | None:
    """
    Fetches live quote from Twelve Data /quote endpoint.
    Returns parsed price dict or None.
    """
    data = _td_request("quote", {"symbol": td_symbol})
    if not data:
        return None
    try:
        def _f(v, fb=0.0):
            try: return float(v) if v else fb
            except: return fb

        close      = _f(data.get("close"))
        prev_close = _f(data.get("previous_close"), close)
        change     = round(close - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0

        w52 = data.get("fifty_two_week", {})

        return {
            "display_name":  data.get("name") or td_symbol.replace(":NSE",""),
            "current_price": round(close, 2),
            "open":          round(_f(data.get("open")), 2),
            "high":          round(_f(data.get("high")), 2),
            "low":           round(_f(data.get("low")),  2),
            "prev_close":    round(prev_close, 2),
            "change":        change,
            "change_pct":    change_pct,
            "volume":        int(_f(data.get("volume"), 0)),
            "avg_volume":    int(_f(data.get("average_volume"), 0)),
            "week_52_high":  round(_f(w52.get("high")), 2),
            "week_52_low":   round(_f(w52.get("low")),  2),
            "sector":        "N/A",
            "industry":      "N/A",
            "market_cap":    0,
            "is_market_open": data.get("is_market_open", False),
        }
    except Exception as e:
        print(f"[price] Twelve Data quote parse error: {e}")
        return None


def _td_ohlcv(td_symbol: str, outputsize: int = 260) -> pd.DataFrame:
    """
    Fetches historical OHLCV from Twelve Data /time_series endpoint.
    outputsize=260 gives ~1 year of daily data (enough for EMA200).
    Returns pandas DataFrame or empty DataFrame.
    """
    data = _td_request("time_series", {
        "symbol":     td_symbol,
        "interval":   "1day",
        "outputsize": outputsize,
    })
    if not data or "values" not in data:
        return pd.DataFrame()
    try:
        rows = []
        for v in data["values"]:
            rows.append({
                "Date":   v["datetime"],
                "Open":   float(v["open"]),
                "High":   float(v["high"]),
                "Low":    float(v["low"]),
                "Close":  float(v["close"]),
                "Volume": float(v.get("volume", 0)),
            })
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)
        df.sort_index(inplace=True)   # oldest first
        return df[["Open","High","Low","Close","Volume"]].dropna()
    except Exception as e:
        print(f"[price] Twelve Data OHLCV parse error: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# NSE Session — secondary fallback (works on Indian IPs)
# ─────────────────────────────────────────────────────────────

class _NSESession:
    BASE = "https://www.nseindia.com"
    _H   = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.nseindia.com/",
    }
    def __init__(self):
        self._s    = None
        self._ts   = 0
        self._lock = threading.Lock()

    def _init(self):
        if self._s and (time.time() - self._ts) < 300:
            return
        s = requests.Session()
        s.headers.update(self._H)
        try:
            s.get(self.BASE, timeout=8)
            time.sleep(0.5)
        except Exception:
            pass
        self._s  = s
        self._ts = time.time()

    def get(self, url: str) -> dict | None:
        with self._lock:
            self._init()
        try:
            r = self._s.get(url, timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return None


_nse = _NSESession()


def _nse_quote(nse_sym: str) -> dict | None:
    data = _nse.get(
        f"https://www.nseindia.com/api/quote-equity?symbol={nse_sym}")
    if not data:
        return None
    try:
        def _f(v, fb=0.0):
            try: return float(v) if v is not None else fb
            except: return fb

        pd_  = data.get("priceInfo", {})
        info = data.get("info", {})
        meta = data.get("metadata", {})
        ltp  = pd_.get("lastPrice") or pd_.get("close")
        if not ltp:
            return None

        ltp_f  = _f(ltp)
        prev_f = _f(pd_.get("previousClose") or pd_.get("close"), ltp_f)
        w52    = pd_.get("weekHighLow", {})

        return {
            "display_name":  (info.get("companyName") or
                              meta.get("companyName") or nse_sym),
            "current_price": round(ltp_f, 2),
            "open":  round(_f(pd_.get("open"), ltp_f), 2),
            "high":  round(_f((pd_.get("intraDayHighLow") or {}).get("max") or
                              pd_.get("high"), ltp_f), 2),
            "low":   round(_f((pd_.get("intraDayHighLow") or {}).get("min") or
                              pd_.get("low"), ltp_f), 2),
            "prev_close":    round(prev_f, 2),
            "change":        round(ltp_f - prev_f, 2),
            "change_pct":    round((ltp_f - prev_f) / prev_f * 100, 2) if prev_f else 0,
            "volume":        int(_f((data.get("marketDeptOrderBook") or {})
                                    .get("tradeInfo", {})
                                    .get("totalTradedVolume"), 0)),
            "avg_volume":    0,
            "week_52_high":  round(_f(w52.get("max"), 0), 2),
            "week_52_low":   round(_f(w52.get("min"), 0), 2),
            "sector":        info.get("sector")   or "N/A",
            "industry":      info.get("industry") or "N/A",
            "market_cap":    0,
            "is_market_open": True,
        }
    except Exception as e:
        print(f"[price] NSE parse error for {nse_sym}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def fetch_stock_data(symbol: str) -> dict:
    """
    Fetches complete price snapshot.
    Priority: Cache → Twelve Data → NSE → Stale cache → Error
    """
    nse_sym, td_sym = resolve_ticker(symbol)
    cache_key       = f"price:{nse_sym}"
    market_status   = is_market_open()

    # 1. Cache hit
    cached = _price_cache.get(cache_key)
    if cached:
        cached["market_status"] = market_status
        return cached

    # 2. Twelve Data (primary — works from any server)
    quote = None
    if TWELVE_DATA_KEY:
        quote = _td_quote(td_sym)
        if quote:
            print(f"[price] Twelve Data OK for {nse_sym}")

    # 3. NSE fallback (works on Indian IPs)
    if quote is None:
        print(f"[price] Twelve Data failed for {nse_sym}, trying NSE...")
        quote = _nse_quote(nse_sym)

    # 4. Stale cache as last resort
    if quote is None:
        stale = _price_cache.get_stale(cache_key)
        if stale:
            print(f"[price] Using stale cache for {nse_sym}")
            as_of = stale.get("price_label", "")
            stale["price_label"]   = f"Last known price · {as_of}"
            stale["market_status"] = market_status
            return stale
        return _error_result(nse_sym,
            f"Could not fetch price for '{symbol}'. "
            f"Please check that '{nse_sym}' is a valid NSE symbol.")

    # Build price label
    if market_status["is_open"]:
        price_label = "Live price"
    else:
        as_of = market_status["as_of_date"].strftime("%d %b %Y")
        labels = {
            "holiday":     f"Closing price (CSP) — market holiday · as of {as_of}",
            "weekend":     f"Closing price (CSP) — weekend · as of {as_of}",
            "after_hours": f"Closing price (CSP) — market closed · as of {as_of}",
            "pre_market":  f"Closing price (CSP) — pre-market · as of {as_of}",
        }
        price_label = labels.get(market_status["reason"],
                                  f"Closing price · as of {as_of}")

    result = {
        "symbol":        f"{nse_sym}.NS",
        "nse_symbol":    nse_sym,
        "display_name":  quote["display_name"],
        "current_price": quote["current_price"],
        "price_label":   price_label,
        "open":          quote["open"],
        "high":          quote["high"],
        "low":           quote["low"],
        "prev_close":    quote["prev_close"],
        "change":        quote["change"],
        "change_pct":    quote["change_pct"],
        "volume":        quote["volume"],
        "avg_volume":    quote.get("avg_volume", 0),
        "week_52_high":  quote["week_52_high"],
        "week_52_low":   quote["week_52_low"],
        "market_cap":    quote.get("market_cap", 0),
        "sector":        quote.get("sector",   "N/A"),
        "industry":      quote.get("industry", "N/A"),
        "market_status": market_status,
        "error":         None,
    }

    _price_cache.set(cache_key, result)
    return result


def fetch_ohlcv_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    """
    Returns OHLCV DataFrame for technical analysis.
    Priority: Cache → Twelve Data → NSE → Stale cache → Empty
    260 candles = ~1 year = enough for EMA200.
    """
    nse_sym, td_sym = resolve_ticker(symbol)
    cache_key       = f"ohlcv:{nse_sym}"

    # Cache hit
    cached = _ohlcv_cache.get(cache_key)
    if cached is not None and not cached.empty:
        return cached

    df = pd.DataFrame()

    # Twelve Data primary
    if TWELVE_DATA_KEY:
        df = _td_ohlcv(td_sym, outputsize=260)
        if not df.empty:
            print(f"[price] Twelve Data OHLCV OK for {nse_sym} ({len(df)} rows)")

    # Stale cache fallback
    if df.empty:
        stale = _ohlcv_cache.get_stale(cache_key)
        if stale is not None and not stale.empty:
            print(f"[price] Using stale OHLCV cache for {nse_sym}")
            return stale

    if not df.empty:
        _ohlcv_cache.set(cache_key, df)

    return df


def _error_result(symbol: str, msg: str) -> dict:
    return {
        "symbol": f"{symbol}.NS", "nse_symbol": symbol,
        "display_name": symbol, "current_price": None,
        "price_label": "N/A", "open":0, "high":0, "low":0,
        "prev_close": None, "change":0, "change_pct":0,
        "volume":0, "avg_volume":0,
        "week_52_high":0, "week_52_low":0,
        "market_cap":0, "sector":"N/A", "industry":"N/A",
        "market_status": is_market_open(), "error": msg,
    }
