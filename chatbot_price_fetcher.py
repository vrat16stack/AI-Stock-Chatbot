"""
chatbot_price_fetcher.py  — Rate-limit resistant version
─────────────────────────────────────────────────────────
Root problem: Yahoo Finance (yfinance) blocks IPs that call it too frequently.
At scale (multiple users), this becomes constant.

Permanent solution — 3 layers:
  Layer 1: Smart cache
            - 5 min cache during market hours
            - 6 hour cache after hours / weekends
            - 100 users asking about RELIANCE = 1 actual API call

  Layer 2: NSE India API (primary for live price)
            - Direct from NSE website, no rate limiting
            - Works on Indian IPs (Render India region)

  Layer 3: yfinance with retry + backoff (fallback)
            - Only called when cache is empty AND NSE fails
            - 3 retries with increasing wait times

  Layer 4: Graceful degradation
            - If all sources fail, return last cached value with a stale label
            - Never show an error to the user if we have ANY recent data
"""

import yfinance as yf
import pandas as pd
import requests
import time
import random
import threading
from datetime import datetime, date, timedelta


# ─────────────────────────────────────────────────────────────
# LAYER 1 — Smart in-memory cache
# ─────────────────────────────────────────────────────────────

class _StockCache:
    def __init__(self):
        self._data: dict = {}
        self._lock = threading.Lock()

    def _ttl(self) -> int:
        """5 min during market hours, 6 hours otherwise."""
        now     = datetime.now()
        weekday = now.weekday()
        if weekday >= 5:
            return 21600
        h, m = now.hour, now.minute
        is_open = (h > 9 or (h == 9 and m >= 15)) and (h < 15 or (h == 15 and m <= 30))
        return 300 if is_open else 21600

    def get(self, key: str):
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            data, ts = entry
            if time.time() - ts > self._ttl():
                del self._data[key]
                return None
            return data

    def get_stale(self, key: str):
        """Returns cached data even if expired — used as last resort."""
        with self._lock:
            entry = self._data.get(key)
            return entry[0] if entry else None

    def set(self, key: str, data):
        with self._lock:
            self._data[key] = (data, time.time())


_cache      = _StockCache()
_ohlcv_cache = _StockCache()


# ─────────────────────────────────────────────────────────────
# NSE Session
# ─────────────────────────────────────────────────────────────

class _NSESession:
    """Browser-like NSE session with auto cookie refresh."""
    BASE = "https://www.nseindia.com"
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

    def __init__(self):
        self._session   = None
        self._last_init = 0
        self._lock      = threading.Lock()

    def _init(self):
        now = time.time()
        if self._session and (now - self._last_init) < 300:
            return
        s = requests.Session()
        s.headers.update(self._HEADERS)
        try:
            s.get(self.BASE, timeout=10)
            time.sleep(random.uniform(0.3, 0.7))
            s.get(f"{self.BASE}/market-data/live-equity-market", timeout=8)
            time.sleep(random.uniform(0.2, 0.5))
        except Exception:
            pass
        self._session   = s
        self._last_init = now

    def get(self, url: str) -> dict | None:
        with self._lock:
            self._init()
        for attempt in range(3):
            try:
                resp = self._session.get(url, timeout=12)
                if resp.status_code in (401, 403):
                    with self._lock:
                        self._last_init = 0
                        self._init()
                    continue
                if resp.status_code == 200:
                    return resp.json()
            except Exception:
                time.sleep(1 + attempt)
        return None


_nse = _NSESession()


# ─────────────────────────────────────────────────────────────
# Holiday detection
# ─────────────────────────────────────────────────────────────

NSE_HOLIDAYS = {
    date(2025, 1, 26), date(2025, 2, 26), date(2025, 3, 14),
    date(2025, 3, 31), date(2025, 4, 10), date(2025, 4, 14),
    date(2025, 4, 18), date(2025, 5, 1),  date(2025, 8, 15),
    date(2025, 8, 27), date(2025, 10, 2), date(2025, 10, 20),
    date(2025, 10, 21),date(2025, 10, 24),date(2025, 11, 5),
    date(2025, 12, 25),
    date(2026, 1, 26), date(2026, 2, 19), date(2026, 3, 28),
    date(2026, 3, 30), date(2026, 4, 2),  date(2026, 4, 10),
    date(2026, 4, 14), date(2026, 5, 1),  date(2026, 8, 15),
    date(2026, 8, 27), date(2026, 10, 2), date(2026, 10, 20),
    date(2026, 10, 21),date(2026, 11, 5), date(2026, 11, 25),
    date(2026, 12, 25),
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

_ALIASES: dict[str, tuple[str, str]] = {
    "RELIANCE":("RELIANCE","RELIANCE.NS"),"RIL":("RELIANCE","RELIANCE.NS"),
    "TCS":("TCS","TCS.NS"),
    "INFY":("INFY","INFY.NS"),"INFOSYS":("INFY","INFY.NS"),
    "WIPRO":("WIPRO","WIPRO.NS"),
    "HCLTECH":("HCLTECH","HCLTECH.NS"),"HCL":("HCLTECH","HCLTECH.NS"),
    "TECHM":("TECHM","TECHM.NS"),"TECHMAHINDRA":("TECHM","TECHM.NS"),
    "HDFCBANK":("HDFCBANK","HDFCBANK.NS"),"HDFC":("HDFCBANK","HDFCBANK.NS"),
    "ICICIBANK":("ICICIBANK","ICICIBANK.NS"),"ICICI":("ICICIBANK","ICICIBANK.NS"),
    "SBIN":("SBIN","SBIN.NS"),"SBI":("SBIN","SBIN.NS"),
    "KOTAKBANK":("KOTAKBANK","KOTAKBANK.NS"),"KOTAK":("KOTAKBANK","KOTAKBANK.NS"),
    "AXISBANK":("AXISBANK","AXISBANK.NS"),"AXIS":("AXISBANK","AXISBANK.NS"),
    "INDUSINDBK":("INDUSINDBK","INDUSINDBK.NS"),"INDUSIND":("INDUSINDBK","INDUSINDBK.NS"),
    "FEDERALBNK":("FEDERALBNK","FEDERALBNK.NS"),
    "IDFCFIRSTB":("IDFCFIRSTB","IDFCFIRSTB.NS"),"IDFC":("IDFCFIRSTB","IDFCFIRSTB.NS"),
    "TATAMOTORS":("TATAMOTORS","TATAMOTORS.NS"),"TATAMOTOR":("TATAMOTORS","TATAMOTORS.NS"),
    "TATASTEEL":("TATASTEEL","TATASTEEL.NS"),
    "TATAPOWER":("TATAPOWER","TATAPOWER.NS"),
    "TATACONSUM":("TATACONSUM","TATACONSUM.NS"),"TATACONSUMER":("TATACONSUM","TATACONSUM.NS"),
    "MARUTI":("MARUTI","MARUTI.NS"),
    "BAJFINANCE":("BAJFINANCE","BAJFINANCE.NS"),"BAJAJFIN":("BAJFINANCE","BAJFINANCE.NS"),
    "BAJAJFINSV":("BAJAJFINSV","BAJAJFINSV.NS"),"BAJAJFINSERV":("BAJAJFINSV","BAJAJFINSV.NS"),
    "BAJAJAUTO":("BAJAJ-AUTO","BAJAJ-AUTO.NS"),"BAJAJ-AUTO":("BAJAJ-AUTO","BAJAJ-AUTO.NS"),
    "HEROMOTOCO":("HEROMOTOCO","HEROMOTOCO.NS"),"HERO":("HEROMOTOCO","HEROMOTOCO.NS"),
    "EICHERMOT":("EICHERMOT","EICHERMOT.NS"),"EICHER":("EICHERMOT","EICHERMOT.NS"),
    "SUNPHARMA":("SUNPHARMA","SUNPHARMA.NS"),"SUN":("SUNPHARMA","SUNPHARMA.NS"),
    "DRREDDY":("DRREDDY","DRREDDY.NS"),"DRREDDYS":("DRREDDY","DRREDDY.NS"),
    "CIPLA":("CIPLA","CIPLA.NS"),
    "DIVISLAB":("DIVISLAB","DIVISLAB.NS"),"DIVIS":("DIVISLAB","DIVISLAB.NS"),
    "ASIANPAINT":("ASIANPAINT","ASIANPAINT.NS"),"ASIAN":("ASIANPAINT","ASIANPAINT.NS"),
    "ULTRACEMCO":("ULTRACEMCO","ULTRACEMCO.NS"),"ULTRATECH":("ULTRACEMCO","ULTRACEMCO.NS"),
    "TITAN":("TITAN","TITAN.NS"),
    "NESTLEIND":("NESTLEIND","NESTLEIND.NS"),"NESTLE":("NESTLEIND","NESTLEIND.NS"),
    "BRITANNIA":("BRITANNIA","BRITANNIA.NS"),
    "HINDALCO":("HINDALCO","HINDALCO.NS"),
    "ONGC":("ONGC","ONGC.NS"),
    "NTPC":("NTPC","NTPC.NS"),
    "POWERGRID":("POWERGRID","POWERGRID.NS"),
    "ADANIPORTS":("ADANIPORTS","ADANIPORTS.NS"),"ADANI":("ADANIPORTS","ADANIPORTS.NS"),
    "ADANIGREEN":("ADANIGREEN","ADANIGREEN.NS"),
    "ADANIENT":("ADANIENT","ADANIENT.NS"),
    "BHARTIARTL":("BHARTIARTL","BHARTIARTL.NS"),"AIRTEL":("BHARTIARTL","BHARTIARTL.NS"),
    "ZOMATO":("ZOMATO","ZOMATO.NS"),
    "IRCTC":("IRCTC","IRCTC.NS"),
    "DMART":("DMART","DMART.NS"),"AVENUESUPER":("DMART","DMART.NS"),
    "NYKAA":("NYKAA","NYKAA.NS"),"FSNNEC":("NYKAA","NYKAA.NS"),
    "PAYTM":("PAYTM","PAYTM.NS"),
    "POLICYBZR":("POLICYBZR","POLICYBZR.NS"),"POLICYBAZAAR":("POLICYBZR","POLICYBZR.NS"),
    "NAUKRI":("NAUKRI","NAUKRI.NS"),"INFOEDGE":("NAUKRI","NAUKRI.NS"),
    "PIDILITIND":("PIDILITIND","PIDILITIND.NS"),"PIDILITE":("PIDILITIND","PIDILITIND.NS"),
    "HAVELLS":("HAVELLS","HAVELLS.NS"),
    "SIEMENS":("SIEMENS","SIEMENS.NS"),
    "ABB":("ABB","ABB.NS"),
    "COLPAL":("COLPAL","COLPAL.NS"),"COLGATE":("COLPAL","COLPAL.NS"),
    "BERGEPAINT":("BERGEPAINT","BERGEPAINT.NS"),"BERGER":("BERGEPAINT","BERGEPAINT.NS"),
    "JSWSTEEL":("JSWSTEEL","JSWSTEEL.NS"),"JSW":("JSWSTEEL","JSWSTEEL.NS"),
    "LTIM":("LTIM","LTIM.NS"),"LTIMINDTREE":("LTIM","LTIM.NS"),"LTI":("LTIM","LTIM.NS"),
    "APOLLOHOSP":("APOLLOHOSP","APOLLOHOSP.NS"),"APOLLO":("APOLLOHOSP","APOLLOHOSP.NS"),
    "MUTHOOTFIN":("MUTHOOTFIN","MUTHOOTFIN.NS"),"MUTHOOT":("MUTHOOTFIN","MUTHOOTFIN.NS"),
    "COALINDIA":("COALINDIA","COALINDIA.NS"),
    "GRASIM":("GRASIM","GRASIM.NS"),
    "TRENT":("TRENT","TRENT.NS"),
    "DIXON":("DIXON","DIXON.NS"),
    "POLYCAB":("POLYCAB","POLYCAB.NS"),
    "KEI":("KEI","KEI.NS"),
    "SUZLON":("SUZLON","SUZLON.NS"),
    "WAAREEENER":("WAAREEENER","WAAREEENER.NS"),"WAAREE":("WAAREEENER","WAAREEENER.NS"),
    "KALYANKJIL":("KALYANKJIL","KALYANKJIL.NS"),"KALYAN":("KALYANKJIL","KALYANKJIL.NS"),
    "GAIL":("GAIL","GAIL.NS"),
    "ITC":("ITC","ITC.NS"),
    "LT":("LT","LT.NS"),
    "PERSISTENT":("PERSISTENT","PERSISTENT.NS"),
    "COFORGE":("COFORGE","COFORGE.NS"),
    "MPHASIS":("MPHASIS","MPHASIS.NS"),
    "HDFCLIFE":("HDFCLIFE","HDFCLIFE.NS"),
    "SBILIFE":("SBILIFE","SBILIFE.NS"),
    "ICICIGI":("ICICIGI","ICICIGI.NS"),
    "CHOLAFIN":("CHOLAFIN","CHOLAFIN.NS"),
    "DLF":("DLF","DLF.NS"),
    "GODREJPROP":("GODREJPROP","GODREJPROP.NS"),
    "OBEROIRLTY":("OBEROIRLTY","OBEROIRLTY.NS"),
    "PRESTIGE":("PRESTIGE","PRESTIGE.NS"),
    "CANBK":("CANBK","CANBK.NS"),
    "BANKBARODA":("BANKBARODA","BANKBARODA.NS"),
    "PNB":("PNB","PNB.NS"),
    "NHPC":("NHPC","NHPC.NS"),
    "JSWENERGY":("JSWENERGY","JSWENERGY.NS"),
    "TORNTPOWER":("TORNTPOWER","TORNTPOWER.NS"),
}


def resolve_ticker(symbol: str) -> tuple[str, str]:
    """Returns (nse_symbol, yf_ticker). e.g. 'reliance' → ('RELIANCE','RELIANCE.NS')"""
    s = symbol.strip().upper().replace(" ","").replace(".","").replace("-","")
    if symbol.strip().upper().endswith(".NS"):
        nse = symbol.strip().upper().replace(".NS","")
        return nse, f"{nse}.NS"
    if s in _ALIASES: return _ALIASES[s]
    return s, f"{s}.NS"


# ─────────────────────────────────────────────────────────────
# LAYER 2 — NSE quote (primary)
# ─────────────────────────────────────────────────────────────

def _nse_quote(nse_sym: str) -> dict | None:
    data = _nse.get(f"https://www.nseindia.com/api/quote-equity?symbol={nse_sym}")
    if not data:
        return None
    try:
        def _f(v, fb=0.0):
            try: return float(v) if v is not None else fb
            except: return fb

        pd_  = data.get("priceInfo", {})
        info = data.get("info", {})
        meta = data.get("metadata", {})

        ltp = pd_.get("lastPrice") or pd_.get("close")
        if ltp is None: return None

        ltp_f  = _f(ltp)
        prev_f = _f(pd_.get("previousClose") or pd_.get("close"), ltp_f)
        w52    = pd_.get("weekHighLow", {})

        return {
            "display_name":  info.get("companyName") or meta.get("companyName") or nse_sym,
            "current_price": round(ltp_f, 2),
            "open":          round(_f(pd_.get("open"), ltp_f), 2),
            "high":          round(_f((pd_.get("intraDayHighLow") or {}).get("max") or pd_.get("high"), ltp_f), 2),
            "low":           round(_f((pd_.get("intraDayHighLow") or {}).get("min") or pd_.get("low"),  ltp_f), 2),
            "prev_close":    round(prev_f, 2),
            "change":        round(ltp_f - prev_f, 2),
            "change_pct":    round((ltp_f - prev_f) / prev_f * 100, 2) if prev_f else 0,
            "volume":        int(_f((data.get("marketDeptOrderBook") or {}).get("tradeInfo", {}).get("totalTradedVolume"), 0)),
            "week_52_high":  round(_f(w52.get("max"), 0), 2),
            "week_52_low":   round(_f(w52.get("min"), 0), 2),
            "sector":        info.get("sector")   or "N/A",
            "industry":      info.get("industry") or "N/A",
            "market_cap":    0,
        }
    except Exception as e:
        print(f"[price] NSE parse error for {nse_sym}: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# LAYER 3 — yfinance with retry + backoff (fallback)
# ─────────────────────────────────────────────────────────────

def _yf_price(yf_sym: str) -> dict | None:
    """yfinance with 3 retries and exponential backoff."""
    for attempt in range(3):
        try:
            wait = (2 ** attempt) + random.uniform(0, 1)
            if attempt > 0:
                print(f"[price] yfinance retry {attempt}/3 for {yf_sym}, waiting {wait:.1f}s")
                time.sleep(wait)

            df = yf.download(
                yf_sym, period="5d", interval="1d",
                progress=False, auto_adjust=True,
            )
            if df is None or df.empty:
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            import math
            close = float(df["Close"].iloc[-1])
            if math.isnan(close): continue

            prev  = float(df["Close"].iloc[-2]) if len(df) >= 2 else close
            if math.isnan(prev): prev = close

            # 52W from 1y data
            w52_high = w52_low = 0
            try:
                df1y = yf.download(yf_sym, period="1y", interval="1d",
                                   progress=False, auto_adjust=True)
                if isinstance(df1y.columns, pd.MultiIndex):
                    df1y.columns = df1y.columns.get_level_values(0)
                if not df1y.empty:
                    w52_high = round(float(df1y["High"].max()), 2)
                    w52_low  = round(float(df1y["Low"].min()),  2)
            except Exception:
                pass

            return {
                "display_name":  yf_sym.replace(".NS",""),
                "current_price": round(close, 2),
                "open":  round(float(df["Open"].iloc[-1]),  2),
                "high":  round(float(df["High"].iloc[-1]),  2),
                "low":   round(float(df["Low"].iloc[-1]),   2),
                "prev_close":   round(prev, 2),
                "change":       round(close - prev, 2),
                "change_pct":   round((close - prev) / prev * 100, 2) if prev else 0,
                "volume":       int(df["Volume"].iloc[-1]),
                "week_52_high": w52_high,
                "week_52_low":  w52_low,
                "sector":   "N/A", "industry": "N/A", "market_cap": 0,
            }
        except Exception as e:
            msg = str(e).lower()
            if "too many requests" in msg or "rate limit" in msg or "403" in msg:
                print(f"[price] yfinance rate limited for {yf_sym}, attempt {attempt+1}/3")
            else:
                print(f"[price] yfinance error for {yf_sym}: {e}")
    return None


def _yf_ohlcv(yf_sym: str) -> pd.DataFrame:
    """yfinance OHLCV with retry."""
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep((2 ** attempt) + random.uniform(0, 1))
            df = yf.download(yf_sym, period="1y", interval="1d",
                             progress=False, auto_adjust=True)
            if df is None or df.empty: continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)
            return df[["Open","High","Low","Close","Volume"]].dropna()
        except Exception as e:
            msg = str(e).lower()
            if "too many requests" in msg or "rate limit" in msg:
                print(f"[price] yfinance OHLCV rate limited for {yf_sym}, attempt {attempt+1}/3")
            else:
                print(f"[price] yfinance OHLCV error: {e}")
    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def fetch_stock_data(symbol: str) -> dict:
    """
    Fetch price with 3-layer fallback + smart cache.
    Cache hit → instant, no API call.
    Cache miss → NSE → yfinance → stale cache → error.
    """
    nse_sym, yf_sym = resolve_ticker(symbol)
    cache_key       = f"price:{nse_sym}"
    market_status   = is_market_open()

    # ── Layer 1: Cache hit ────────────────────────────────────
    cached = _cache.get(cache_key)
    if cached:
        cached["market_status"] = market_status
        return cached

    # ── Layer 2: NSE API ──────────────────────────────────────
    quote = _nse_quote(nse_sym)

    # ── Layer 3: yfinance fallback ────────────────────────────
    if quote is None:
        print(f"[price] NSE failed for {nse_sym}, trying yfinance...")
        quote = _yf_price(yf_sym)

    # ── Layer 4: Stale cache (last resort) ────────────────────
    if quote is None:
        stale = _cache.get_stale(cache_key)
        if stale:
            print(f"[price] Using stale cache for {nse_sym}")
            stale["price_label"] = f"Stale data — refresh failed · {stale.get('price_label','')}"
            stale["market_status"] = market_status
            return stale
        return _error_result(nse_sym,
            f"Could not fetch price for '{symbol}'. "
            f"Check that '{nse_sym}' is a valid NSE symbol.")

    # Fix 52W H/L if NSE returned 0
    if not quote.get("week_52_high") or quote["week_52_high"] == 0:
        try:
            df1y = _yf_ohlcv(yf_sym)
            if not df1y.empty:
                quote["week_52_high"] = round(float(df1y["High"].max()), 2)
                quote["week_52_low"]  = round(float(df1y["Low"].min()),  2)
        except Exception:
            pass

    # Price label
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
        price_label = labels.get(market_status["reason"], f"Closing price · as of {as_of}")

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
        "avg_volume":    0,
        "week_52_high":  quote["week_52_high"],
        "week_52_low":   quote["week_52_low"],
        "market_cap":    quote.get("market_cap", 0),
        "sector":        quote.get("sector",   "N/A"),
        "industry":      quote.get("industry", "N/A"),
        "market_status": market_status,
        "error":         None,
    }

    _cache.set(cache_key, result)
    return result


def fetch_ohlcv_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    """
    Returns OHLCV DataFrame with cache.
    OHLCV is cached for 1 hour — it doesn't change often.
    """
    nse_sym, yf_sym = resolve_ticker(symbol)
    cache_key       = f"ohlcv:{nse_sym}"

    cached = _ohlcv_cache.get(cache_key)
    if cached is not None and not cached.empty:
        return cached

    df = _yf_ohlcv(yf_sym)

    if not df.empty:
        _ohlcv_cache.set(cache_key, df)
    else:
        stale = _ohlcv_cache.get_stale(cache_key)
        if stale is not None and not stale.empty:
            print(f"[price] Using stale OHLCV cache for {nse_sym}")
            return stale

    return df


def _error_result(symbol: str, msg: str) -> dict:
    return {
        "symbol": f"{symbol}.NS", "nse_symbol": symbol,
        "display_name": symbol, "current_price": None,
        "price_label": "N/A", "open": 0, "high": 0, "low": 0,
        "prev_close": None, "change": 0, "change_pct": 0,
        "volume": 0, "avg_volume": 0, "week_52_high": 0, "week_52_low": 0,
        "market_cap": 0, "sector": "N/A", "industry": "N/A",
        "market_status": is_market_open(), "error": msg,
    }
