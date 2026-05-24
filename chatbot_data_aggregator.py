"""
chatbot_data_aggregator.py
───────────────────────────
Phase 1 — Data Aggregator

Single entry point that fires all three data fetches in parallel
and returns one clean unified payload for the analysis engine.

Usage:
    from chatbot_data_aggregator import get_full_stock_data, get_market_context

    data = get_full_stock_data("RELIANCE")
    ctx  = get_market_context()
"""

import concurrent.futures
from chatbot_price_fetcher  import fetch_stock_data, fetch_ohlcv_history
from chatbot_fundamentals   import fetch_fundamentals
from chatbot_news_fetcher   import fetch_news, format_news_for_prompt


def get_full_stock_data(symbol: str) -> dict:
    """
    Fetches price + fundamentals + news in parallel.

    Returns:
    {
        'symbol':        str,
        'display_name':  str,
        'price_data':    dict,     # from chatbot_price_fetcher
        'fundamentals':  dict,     # from chatbot_fundamentals
        'news':          dict,     # from chatbot_news_fetcher
        'news_prompt':   str,      # pre-formatted for Groq prompt
        'ohlcv':         DataFrame,# for technical analysis (Phase 2)
        'has_errors':    bool,
        'error_summary': str | None,
    }
    """

    # ── Fire all fetches in parallel ──────────────────────────────────────────
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        price_f  = ex.submit(fetch_stock_data,    symbol)
        fund_f   = ex.submit(fetch_fundamentals,  symbol)
        news_f   = ex.submit(fetch_news,          symbol)
        ohlcv_f  = ex.submit(fetch_ohlcv_history, symbol, "1y")

    price_data = price_f.result()
    fund_data  = fund_f.result()
    news_data  = news_f.result()
    ohlcv      = ohlcv_f.result()

    # ── If we got a display name, re-fetch news with it for better results ────
    display_name = price_data.get("display_name") or symbol.upper()
    if display_name and display_name != symbol.upper():
        enriched_news = fetch_news(symbol, company_name=display_name)
        if enriched_news["total_fetched"] > news_data["total_fetched"]:
            news_data = enriched_news

    # ── Collect errors ────────────────────────────────────────────────────────
    errors = []
    if price_data.get("error"):
        errors.append(f"Price: {price_data['error']}")
    if fund_data.get("error"):
        errors.append(f"Fundamentals: {fund_data['error']}")
    if news_data.get("error"):
        errors.append(f"News: {news_data['error']}")
    if ohlcv.empty:
        errors.append("OHLCV history unavailable — technical analysis will be limited.")

    return {
        "symbol":        price_data.get("symbol", symbol),
        "display_name":  display_name,
        "price_data":    price_data,
        "fundamentals":  fund_data,
        "news":          news_data,
        "news_prompt":   format_news_for_prompt(news_data),
        "ohlcv":         ohlcv,
        "has_errors":    bool(errors),
        "error_summary": " | ".join(errors) if errors else None,
    }


def get_market_context() -> dict:
    """
    Fetches Nifty 50 + Sensex for broad market direction context.
    Uses NSE index API directly — no yfinance needed.
    """
    def _fetch_index(index_name: str) -> dict:
        """Fetch index data from NSE API."""
        try:
            from chatbot_price_fetcher import _NSE
            url  = f"https://www.nseindia.com/api/allIndices"
            data = _NSE.get(url)
            if data and "data" in data:
                for idx in data["data"]:
                    idx_name = idx.get("index", "").upper().strip()
                    if idx_name == index_name.upper() or index_name.upper() in idx_name:
                        last   = float(idx.get("last", 0))
                        prev   = float(idx.get("previousClose", last))
                        change = round(last - prev, 2)
                        chg_pct= round((change / prev) * 100, 2) if prev else 0
                        return {"price": round(last, 2), "change_pct": chg_pct}
        except Exception:
            pass
        return {"price": None, "change_pct": 0}

    nifty  = _fetch_index("Nifty 50")
    sensex = _fetch_index("Sensex")

    n_chg = nifty.get("change_pct")  or 0
    s_chg = sensex.get("change_pct") or 0
    avg   = (n_chg + s_chg) / 2

    mood = "bullish" if avg > 0.5 else "bearish" if avg < -0.5 else "sideways/neutral"

    from chatbot_price_fetcher import is_market_open
    return {
        "nifty50_price":   nifty.get("price"),
        "nifty50_change":  n_chg,
        "sensex_price":    sensex.get("price"),
        "sensex_change":   s_chg,
        "market_mood":     mood,
        "market_status":   is_market_open(),
    }