"""
chatbot_price_fetcher.py
─────────────────────────
Phase 1 — Price Data Layer  (NSE-first, no rate limiting)

Data sources (in order of priority):
  1. NSE India API  — primary, free, no key, no rate limit
  2. yfinance       — fallback only if NSE fails

NSE endpoints used:
  Quote  : https://www.nseindia.com/api/quote-equity?symbol=RELIANCE
  OHLCV  : https://www.nseindia.com/api/chart-databyindex?index=RELIANCE&indices=false
"""

import requests
import pandas as pd
import time
import random
import json
from datetime import datetime, date, timedelta


# ─────────────────────────────────────────────────────────────
# NSE Session — must mimic a browser visit to get cookies
# ─────────────────────────────────────────────────────────────

class NSESession:
    """
    NSE requires a browser-like session with cookies from the homepage.
    This class handles that automatically.
    """
    BASE = "https://www.nseindia.com"
    HEADERS = {
        "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         "https://www.nseindia.com/",
        "Connection":      "keep-alive",
        "sec-ch-ua":       '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile":"?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest":  "empty",
        "Sec-Fetch-Mode":  "cors",
        "Sec-Fetch-Site":  "same-origin",
    }

    def __init__(self):
        self._session   = None
        self._last_init = 0

    def _init_session(self):
        """Visit NSE homepage to get cookies. Re-initialises if > 5 min old."""
        now = time.time()
        if self._session and (now - self._last_init) < 300:
            return  # reuse existing session

        s = requests.Session()
        s.headers.update(self.HEADERS)
        try:
            # Homepage visit — sets NSE cookies
            s.get(self.BASE, timeout=10)
            time.sleep(random.uniform(0.3, 0.7))
            # Market status page — strengthens cookie validity
            s.get(f"{self.BASE}/market-data/live-equity-market", timeout=8)
            time.sleep(random.uniform(0.2, 0.5))
        except Exception:
            pass
        self._session   = s
        self._last_init = now

    def get(self, url: str, retries: int = 3) -> dict | None:
        """GET request with auto cookie refresh and retry."""
        self._init_session()
        for attempt in range(retries):
            try:
                resp = self._session.get(url, timeout=12)
                if resp.status_code == 401 or resp.status_code == 403:
                    # Cookies expired — force refresh
                    self._last_init = 0
                    self._init_session()
                    continue
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(1 + attempt)
        return None


_NSE = NSESession()


# ─────────────────────────────────────────────────────────────
# SECTION 1 — Market Status & Holiday Detection
# ─────────────────────────────────────────────────────────────

NSE_HOLIDAYS_FALLBACK = {
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

_holiday_cache: set | None = None


def _get_nse_holidays() -> set:
    global _holiday_cache
    if _holiday_cache is not None:
        return _holiday_cache
    try:
        data = _NSE.get("https://www.nseindia.com/api/holiday-master?type=trading")
        if data:
            holidays = set()
            for item in data.get("FO", []):
                try:
                    d = datetime.strptime(item["tradingDate"], "%d-%b-%Y").date()
                    holidays.add(d)
                except Exception:
                    pass
            if holidays:
                _holiday_cache = holidays
                return _holiday_cache
    except Exception:
        pass
    _holiday_cache = NSE_HOLIDAYS_FALLBACK.copy()
    return _holiday_cache


def _last_trading_day(from_date: date) -> date:
    holidays = _get_nse_holidays()
    d = from_date
    for _ in range(14):
        if d.weekday() < 5 and d not in holidays:
            return d
        d -= timedelta(days=1)
    return from_date


def is_market_open() -> dict:
    today    = date.today()
    now      = datetime.now()
    weekday  = today.weekday()
    holidays = _get_nse_holidays()

    if weekday >= 5:
        return {"is_open": False, "reason": "weekend",
                "as_of_date": _last_trading_day(today - timedelta(days=1))}

    if today in holidays:
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
# SECTION 2 — Ticker Resolver
# ─────────────────────────────────────────────────────────────

# Maps user input → (NSE_SYMBOL, yfinance_ticker)
# NSE symbol = plain uppercase, no suffix  e.g. "RELIANCE"
# yf ticker  = with .NS suffix             e.g. "RELIANCE.NS"
_ALIASES: dict[str, tuple[str, str]] = {
    "RELIANCE":     ("RELIANCE",    "RELIANCE.NS"),
    "RIL":          ("RELIANCE",    "RELIANCE.NS"),
    "TCS":          ("TCS",         "TCS.NS"),
    "INFY":         ("INFY",        "INFY.NS"),
    "INFOSYS":      ("INFY",        "INFY.NS"),
    "WIPRO":        ("WIPRO",       "WIPRO.NS"),
    "HCLTECH":      ("HCLTECH",     "HCLTECH.NS"),
    "HCL":          ("HCLTECH",     "HCLTECH.NS"),
    "TECHM":        ("TECHM",       "TECHM.NS"),
    "TECHMAHINDRA": ("TECHM",       "TECHM.NS"),
    "HDFCBANK":     ("HDFCBANK",    "HDFCBANK.NS"),
    "HDFC":         ("HDFCBANK",    "HDFCBANK.NS"),
    "ICICIBANK":    ("ICICIBANK",   "ICICIBANK.NS"),
    "ICICI":        ("ICICIBANK",   "ICICIBANK.NS"),
    "SBIN":         ("SBIN",        "SBIN.NS"),
    "SBI":          ("SBIN",        "SBIN.NS"),
    "KOTAKBANK":    ("KOTAKBANK",   "KOTAKBANK.NS"),
    "KOTAK":        ("KOTAKBANK",   "KOTAKBANK.NS"),
    "AXISBANK":     ("AXISBANK",    "AXISBANK.NS"),
    "AXIS":         ("AXISBANK",    "AXISBANK.NS"),
    "INDUSINDBK":   ("INDUSINDBK",  "INDUSINDBK.NS"),
    "INDUSIND":     ("INDUSINDBK",  "INDUSINDBK.NS"),
    "FEDERALBNK":   ("FEDERALBNK",  "FEDERALBNK.NS"),
    "IDFCFIRSTB":   ("IDFCFIRSTB",  "IDFCFIRSTB.NS"),
    "IDFC":         ("IDFCFIRSTB",  "IDFCFIRSTB.NS"),
    "TATAMOTORS":   ("TATAMOTORS",  "TATAMOTORS.NS"),
    "TATAMOTOR":    ("TATAMOTORS",  "TATAMOTORS.NS"),
    "TATASTEEL":    ("TATASTEEL",   "TATASTEEL.NS"),
    "TATAPOWER":    ("TATAPOWER",   "TATAPOWER.NS"),
    "TATACONSUM":   ("TATACONSUM",  "TATACONSUM.NS"),
    "TATACONSUMER": ("TATACONSUM",  "TATACONSUM.NS"),
    "MARUTI":       ("MARUTI",      "MARUTI.NS"),
    "BAJFINANCE":   ("BAJFINANCE",  "BAJFINANCE.NS"),
    "BAJAJFIN":     ("BAJFINANCE",  "BAJFINANCE.NS"),
    "BAJAJFINSV":   ("BAJAJFINSV",  "BAJAJFINSV.NS"),
    "BAJAJFINSERV": ("BAJAJFINSV",  "BAJAJFINSV.NS"),
    "BAJAJAUTO":    ("BAJAJ-AUTO",  "BAJAJ-AUTO.NS"),
    "BAJAJ-AUTO":   ("BAJAJ-AUTO",  "BAJAJ-AUTO.NS"),
    "HEROMOTOCO":   ("HEROMOTOCO",  "HEROMOTOCO.NS"),
    "HERO":         ("HEROMOTOCO",  "HEROMOTOCO.NS"),
    "EICHERMOT":    ("EICHERMOT",   "EICHERMOT.NS"),
    "EICHER":       ("EICHERMOT",   "EICHERMOT.NS"),
    "SUNPHARMA":    ("SUNPHARMA",   "SUNPHARMA.NS"),
    "SUN":          ("SUNPHARMA",   "SUNPHARMA.NS"),
    "DRREDDY":      ("DRREDDY",     "DRREDDY.NS"),
    "DRREDDYS":     ("DRREDDY",     "DRREDDY.NS"),
    "CIPLA":        ("CIPLA",       "CIPLA.NS"),
    "DIVISLAB":     ("DIVISLAB",    "DIVISLAB.NS"),
    "DIVIS":        ("DIVISLAB",    "DIVISLAB.NS"),
    "ASIANPAINT":   ("ASIANPAINT",  "ASIANPAINT.NS"),
    "ASIAN":        ("ASIANPAINT",  "ASIANPAINT.NS"),
    "ULTRACEMCO":   ("ULTRACEMCO",  "ULTRACEMCO.NS"),
    "ULTRATECH":    ("ULTRACEMCO",  "ULTRACEMCO.NS"),
    "TITAN":        ("TITAN",       "TITAN.NS"),
    "NESTLEIND":    ("NESTLEIND",   "NESTLEIND.NS"),
    "NESTLE":       ("NESTLEIND",   "NESTLEIND.NS"),
    "BRITANNIA":    ("BRITANNIA",   "BRITANNIA.NS"),
    "HINDALCO":     ("HINDALCO",    "HINDALCO.NS"),
    "ONGC":         ("ONGC",        "ONGC.NS"),
    "NTPC":         ("NTPC",        "NTPC.NS"),
    "POWERGRID":    ("POWERGRID",   "POWERGRID.NS"),
    "ADANIPORTS":   ("ADANIPORTS",  "ADANIPORTS.NS"),
    "ADANIENT":     ("ADANIENT",    "ADANIENT.NS"),
    "ADANIGREEN":   ("ADANIGREEN",  "ADANIGREEN.NS"),
    "BHARTIARTL":   ("BHARTIARTL",  "BHARTIARTL.NS"),
    "AIRTEL":       ("BHARTIARTL",  "BHARTIARTL.NS"),
    "ZOMATO":       ("ZOMATO",      "ZOMATO.NS"),
    "IRCTC":        ("IRCTC",       "IRCTC.NS"),
    "DMART":        ("DMART",       "DMART.NS"),
    "AVENUESUPER":  ("DMART",       "DMART.NS"),
    "NYKAA":        ("NYKAA",       "NYKAA.NS"),
    "FSNNEC":       ("NYKAA",       "NYKAA.NS"),
    "PAYTM":        ("PAYTM",       "PAYTM.NS"),
    "POLICYBZR":    ("POLICYBZR",   "POLICYBZR.NS"),
    "POLICYBAZAAR": ("POLICYBZR",   "POLICYBZR.NS"),
    "NAUKRI":       ("NAUKRI",      "NAUKRI.NS"),
    "INFOEDGE":     ("NAUKRI",      "NAUKRI.NS"),
    "PIDILITIND":   ("PIDILITIND",  "PIDILITIND.NS"),
    "PIDILITE":     ("PIDILITIND",  "PIDILITIND.NS"),
    "HAVELLS":      ("HAVELLS",     "HAVELLS.NS"),
    "SIEMENS":      ("SIEMENS",     "SIEMENS.NS"),
    "ABB":          ("ABB",         "ABB.NS"),
    "COLPAL":       ("COLPAL",      "COLPAL.NS"),
    "COLGATE":      ("COLPAL",      "COLPAL.NS"),
    "BERGEPAINT":   ("BERGEPAINT",  "BERGEPAINT.NS"),
    "BERGER":       ("BERGEPAINT",  "BERGEPAINT.NS"),
    "JSWSTEEL":     ("JSWSTEEL",    "JSWSTEEL.NS"),
    "JSW":          ("JSWSTEEL",    "JSWSTEEL.NS"),
    "LTIM":         ("LTIM",        "LTIM.NS"),
    "LTIMINDTREE":  ("LTIM",        "LTIM.NS"),
    "LTI":          ("LTIM",        "LTIM.NS"),
    "APOLLOHOSP":   ("APOLLOHOSP",  "APOLLOHOSP.NS"),
    "APOLLO":       ("APOLLOHOSP",  "APOLLOHOSP.NS"),
    "MUTHOOTFIN":   ("MUTHOOTFIN",  "MUTHOOTFIN.NS"),
    "MUTHOOT":      ("MUTHOOTFIN",  "MUTHOOTFIN.NS"),
    "COALINDIA":    ("COALINDIA",   "COALINDIA.NS"),
    "GRASIM":       ("GRASIM",      "GRASIM.NS"),
    "TRENT":        ("TRENT",       "TRENT.NS"),
    "DIXON":        ("DIXON",       "DIXON.NS"),
    "POLYCAB":      ("POLYCAB",     "POLYCAB.NS"),
    "KEI":          ("KEI",         "KEI.NS"),
    "SUZLON":       ("SUZLON",      "SUZLON.NS"),
    "WAAREEENER":   ("WAAREEENER",  "WAAREEENER.NS"),
    "WAAREE":       ("WAAREEENER",  "WAAREEENER.NS"),
    "KALYANKJIL":   ("KALYANKJIL",  "KALYANKJIL.NS"),
    "KALYAN":       ("KALYANKJIL",  "KALYANKJIL.NS"),
    "GAIL":         ("GAIL",        "GAIL.NS"),
    "ITC":          ("ITC",         "ITC.NS"),
    "LT":           ("LT",          "LT.NS"),
    "LTTS":         ("LTTS",        "LTTS.NS"),
    "PERSISTENT":   ("PERSISTENT",  "PERSISTENT.NS"),
    "COFORGE":      ("COFORGE",     "COFORGE.NS"),
    "MPHASIS":      ("MPHASIS",     "MPHASIS.NS"),
    "OFSS":         ("OFSS",        "OFSS.NS"),
    "HDFCLIFE":     ("HDFCLIFE",    "HDFCLIFE.NS"),
    "SBILIFE":      ("SBILIFE",     "SBILIFE.NS"),
    "ICICIGI":      ("ICICIGI",     "ICICIGI.NS"),
    "CHOLAFIN":     ("CHOLAFIN",    "CHOLAFIN.NS"),
    "MANAPPURAM":   ("MANAPPURAM",  "MANAPPURAM.NS"),
    "CANBK":        ("CANBK",       "CANBK.NS"),
    "BANKBARODA":   ("BANKBARODA",  "BANKBARODA.NS"),
    "PNB":          ("PNB",         "PNB.NS"),
    "NHPC":         ("NHPC",        "NHPC.NS"),
    "SJVN":         ("SJVN",        "SJVN.NS"),
    "JSWENERGY":    ("JSWENERGY",   "JSWENERGY.NS"),
    "TORNTPOWER":   ("TORNTPOWER",  "TORNTPOWER.NS"),
    "ADANIPOWER":   ("ADANIPOWER",  "ADANIPOWER.NS"),
    "DLF":          ("DLF",         "DLF.NS"),
    "GODREJPROP":   ("GODREJPROP",  "GODREJPROP.NS"),
    "OBEROIRLTY":   ("OBEROIRLTY",  "OBEROIRLTY.NS"),
    "PRESTIGE":     ("PRESTIGE",    "PRESTIGE.NS"),
    "BRIGADE":      ("BRIGADE",     "BRIGADE.NS"),
}


def resolve_ticker(symbol: str) -> tuple[str, str]:
    """
    Returns (nse_symbol, yf_ticker).
    e.g. 'reliance' → ('RELIANCE', 'RELIANCE.NS')
         'TCS.NS'   → ('TCS',      'TCS.NS')
    """
    s = symbol.strip().upper().replace(" ", "").replace(".", "").replace("-", "")

    # Already has .NS
    if symbol.strip().upper().endswith(".NS"):
        nse = symbol.strip().upper().replace(".NS", "")
        return nse, f"{nse}.NS"

    if s in _ALIASES:
        return _ALIASES[s]

    # Default: treat as NSE symbol
    return s, f"{s}.NS"


# ─────────────────────────────────────────────────────────────
# SECTION 3 — NSE Price Fetch
# ─────────────────────────────────────────────────────────────

def _fetch_nse_quote(nse_symbol: str) -> dict | None:
    """
    Fetches live quote from NSE API.
    Returns parsed dict or None on failure.
    """
    url  = f"https://www.nseindia.com/api/quote-equity?symbol={nse_symbol}"
    data = _NSE.get(url)
    if not data:
        return None

    try:
        pd_  = data.get("priceInfo", {})
        info = data.get("info",      {})
        meta = data.get("metadata",  {})

        def _f(v, fallback=0.0):
            """Safe float — returns fallback if v is None or non-numeric."""
            try:
                return float(v) if v is not None else fallback
            except (TypeError, ValueError):
                return fallback

        ltp       = pd_.get("lastPrice") or pd_.get("close")
        prev_close= pd_.get("previousClose") or pd_.get("close")

        # On weekends/holidays NSE may return lastPrice as None — use close
        if ltp is None:
            ltp = pd_.get("close") or pd_.get("lastPrice")
        if ltp is None:
            return None   # truly no data

        ltp_f  = _f(ltp)
        prev_f = _f(prev_close, ltp_f)

        open_    = pd_.get("open")   or ltp
        high     = (pd_.get("intraDayHighLow", {}).get("max")
                    or pd_.get("high") or ltp)
        low      = (pd_.get("intraDayHighLow", {}).get("min")
                    or pd_.get("low")  or ltp)
        w52_high = pd_.get("weekHighLow", {}).get("max") or 0
        w52_low  = pd_.get("weekHighLow", {}).get("min") or 0
        volume   = (data.get("marketDeptOrderBook", {})
                       .get("tradeInfo", {}).get("totalTradedVolume") or 0)

        change     = round(ltp_f - prev_f, 2)
        change_pct = round((change / prev_f) * 100, 2) if prev_f else 0

        return {
            "display_name":  info.get("companyName") or meta.get("companyName") or nse_symbol,
            "current_price": round(ltp_f, 2),
            "open":          round(_f(open_), 2),
            "high":          round(_f(high),  2),
            "low":           round(_f(low),   2),
            "prev_close":    round(prev_f,    2),
            "change":        change,
            "change_pct":    change_pct,
            "volume":        int(volume),
            "week_52_high":  round(float(w52_high), 2),
            "week_52_low":   round(float(w52_low),  2),
            "sector":        info.get("sector")   or "N/A",
            "industry":      info.get("industry") or "N/A",
            "market_cap":    0,   # NSE API doesn't return marketCap directly
        }
    except Exception as e:
        print(f"[price] NSE parse error for {nse_symbol}: {e}")
        return None


def _fetch_nse_ohlcv(nse_symbol: str, days: int = 365) -> pd.DataFrame:
    """
    Fetches historical OHLCV from NSE chart endpoint.
    Returns DataFrame or empty DataFrame on failure.
    """
    url  = (f"https://www.nseindia.com/api/historical/cm/equity"
            f"?symbol={nse_symbol}&series=[%22EQ%22]"
            f"&from=&to=&csv=true")

    # Use the simpler chart data endpoint instead
    url2 = f"https://www.nseindia.com/api/chart-databyindex?index={nse_symbol}&indices=false"
    data = _NSE.get(url2)

    if data and "grapthData" in data:
        try:
            rows = data["grapthData"]
            records = []
            for row in rows:
                # row = [timestamp_ms, close_price]
                if isinstance(row, list) and len(row) >= 2:
                    dt    = datetime.fromtimestamp(row[0] / 1000)
                    close = float(row[1])
                    records.append({"Date": dt, "Close": close})

            if records:
                df = pd.DataFrame(records)
                df.set_index("Date", inplace=True)
                df.index = pd.to_datetime(df.index)
                # Add placeholder OHLV columns (only Close available from this endpoint)
                df["Open"]   = df["Close"]
                df["High"]   = df["Close"]
                df["Low"]    = df["Close"]
                df["Volume"] = 0
                return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        except Exception as e:
            print(f"[price] NSE chart parse error: {e}")

    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# SECTION 4 — yfinance fallback (used only if NSE fails)
# ─────────────────────────────────────────────────────────────

def _yf_fallback_price(yf_ticker: str) -> dict | None:
    """Last resort — try yfinance with extended wait."""
    try:
        import yfinance as yf
        time.sleep(random.uniform(2, 4))   # longer wait to avoid rate limit
        df = yf.download(yf_ticker, period="5d", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        import math
        close      = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2]) if len(df) >= 2 else close
        # Guard against NaN values from yfinance
        if math.isnan(close) or math.isnan(prev_close):
            return None
        change     = round(close - prev_close, 2)
        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
        return {
            "display_name":  yf_ticker.replace(".NS", ""),
            "current_price": round(close, 2),
            "open":  round(float(df["Open"].iloc[-1]),  2),
            "high":  round(float(df["High"].iloc[-1]),  2),
            "low":   round(float(df["Low"].iloc[-1]),   2),
            "prev_close":  round(prev_close, 2),
            "change":      change,
            "change_pct":  change_pct,
            "volume":      int(df["Volume"].iloc[-1]),
            "week_52_high": 0,
            "week_52_low":  0,
            "sector":   "N/A",
            "industry": "N/A",
            "market_cap": 0,
        }
    except Exception:
        return None


def _yf_fallback_ohlcv(yf_ticker: str) -> pd.DataFrame:
    """Last resort OHLCV via yfinance."""
    try:
        import yfinance as yf
        time.sleep(random.uniform(2, 4))
        df = yf.download(yf_ticker, period="1y", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# SECTION 5 — Public API
# ─────────────────────────────────────────────────────────────

def fetch_stock_data(symbol: str) -> dict:
    """
    Fetches complete price snapshot. NSE-first, yfinance fallback.
    """
    nse_sym, yf_sym = resolve_ticker(symbol)
    market_status   = is_market_open()

    # ── Try NSE first ─────────────────────────────────────────────────────────
    quote = _fetch_nse_quote(nse_sym)

    # ── Fallback to yfinance ──────────────────────────────────────────────────
    if quote is None:
        print(f"[price] NSE failed for {nse_sym}, trying yfinance...")
        quote = _yf_fallback_price(yf_sym)

    if quote is None:
        return _error_result(nse_sym,
            f"Could not fetch price for '{symbol}'. "
            f"Check that '{nse_sym}' is a valid NSE symbol.")

    # Fix 52W H/L if NSE returned 0 - compute from OHLCV history
    if not quote.get("week_52_high") or quote["week_52_high"] == 0:
        try:
            df_1y = _yf_fallback_ohlcv(yf_sym)
            if not df_1y.empty:
                quote["week_52_high"] = round(float(df_1y["High"].max()), 2)
                quote["week_52_low"]  = round(float(df_1y["Low"].min()),  2)
        except Exception:
            pass

    # ── Price label ───────────────────────────────────────────────────────────
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

    return {
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


def fetch_ohlcv_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    """
    Returns OHLCV DataFrame for technical analysis.
    NSE chart endpoint first, yfinance fallback.
    1y → ~250 candles (enough for EMA200).
    """
    nse_sym, yf_sym = resolve_ticker(symbol)

    # Try NSE chart data
    df = _fetch_nse_ohlcv(nse_sym)

    # NSE chart endpoint only returns Close — not enough for ADX/BB/Stoch
    # which need High/Low. Fall back to yfinance for proper OHLCV.
    if df.empty or (df["High"] == df["Close"]).all():
        print(f"[price] NSE OHLCV incomplete for {nse_sym}, trying yfinance...")
        df = _yf_fallback_ohlcv(yf_sym)

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