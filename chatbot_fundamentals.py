"""
chatbot_fundamentals.py
────────────────────────
Phase 1 — Fundamentals Data Layer

Fetches company fundamentals from two sources:
  1. Screener.in (primary — free scraping, no API key)
  2. yfinance    (fallback / supplement for any missing fields)

Mirrors the same fundamental fields used in your stock_scout.py:
  P/E, P/B, RoE, RoCE, D/E, EPS, revenue growth, profit growth,
  promoter holding, FII holding, market cap.
"""

import requests
from bs4 import BeautifulSoup
from chatbot_price_fetcher import resolve_ticker


# ─────────────────────────────────────────────────────────────
# Screener.in URLs
# ─────────────────────────────────────────────────────────────

_SCREENER_CONSOLIDATED = "https://www.screener.in/company/{sym}/consolidated/"
_SCREENER_STANDALONE   = "https://www.screener.in/company/{sym}/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.screener.in/",
}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _clean_num(text: str) -> float | None:
    """Strip ₹, Cr, %, commas and return float."""
    if not text:
        return None
    t = (text.strip()
         .replace(",", "")
         .replace("%", "")
         .replace("₹", "")
         .replace("Cr", "")
         .replace("cr", "")
         .strip())
    try:
        return float(t)
    except ValueError:
        return None


def _screener_symbol(ticker: str) -> str:
    """RELIANCE.NS → RELIANCE"""
    return ticker.replace(".NS", "").replace(".BO", "").upper()


# ─────────────────────────────────────────────────────────────
# Main fetch function
# ─────────────────────────────────────────────────────────────

def fetch_fundamentals(symbol: str) -> dict:
    """
    Returns:
    {
        'pe_ratio':            float | None,
        'pb_ratio':            float | None,
        'roe':                 float | None,   # %
        'roce':                float | None,   # %
        'debt_to_equity':      float | None,
        'eps':                 float | None,
        'revenue_growth_yoy':  float | None,   # %
        'profit_growth_yoy':   float | None,   # %
        'sales_growth_3y':     float | None,   # % per year
        'profit_growth_3y':    float | None,   # % per year
        'current_ratio':       float | None,
        'dividend_yield':      float | None,   # %
        'promoter_holding':    float | None,   # %
        'fii_holding':         float | None,   # %
        'dii_holding':         float | None,   # %
        'market_cap_cr':       float | None,   # in Crores
        'book_value':          float | None,
        'face_value':          float | None,
        'industry_pe':         float | None,
        'source':              'screener' | 'yfinance' | 'partial',
        'error':               None | str,
    }
    """
    nse_sym, yf_ticker = resolve_ticker(symbol)
    ticker        = yf_ticker          # keep variable name for rest of function
    scr_sym       = _screener_symbol(nse_sym)

    # Blank result template
    result = {k: None for k in [
        "pe_ratio", "pb_ratio", "roe", "roce", "debt_to_equity",
        "eps", "revenue_growth_yoy", "profit_growth_yoy",
        "sales_growth_3y", "profit_growth_3y", "current_ratio",
        "dividend_yield", "promoter_holding", "fii_holding",
        "dii_holding", "market_cap_cr", "book_value",
        "face_value", "industry_pe",
    ]}
    result["source"] = "none"
    result["error"]  = None

    # ── 1. Try Screener consolidated, then standalone ─────────────────────────
    scr = _scrape_screener(scr_sym, consolidated=True)
    if scr.get("error"):
        scr = _scrape_screener(scr_sym, consolidated=False)

    if not scr.get("error"):
        result.update({k: v for k, v in scr.items() if k != "error"})
        result["source"] = "screener"

    # ── 2. Fill missing fields from yfinance ──────────────────────────────────
    yf_data = _fetch_yfinance_fundamentals(ticker)
    filled  = False
    for k, v in yf_data.items():
        if result.get(k) is None and v is not None:
            result[k] = v
            filled = True

    if filled and result["source"] == "none":
        result["source"] = "yfinance"
    elif filled and result["source"] == "screener":
        result["source"] = "partial"   # screener + yfinance combined

    return result


# ─────────────────────────────────────────────────────────────
# Screener.in scraper
# ─────────────────────────────────────────────────────────────

def _scrape_screener(sym: str, consolidated: bool) -> dict:
    url = (_SCREENER_CONSOLIDATED if consolidated else _SCREENER_STANDALONE).format(sym=sym)
    data = {}

    try:
        r = requests.get(url, headers=_HEADERS, timeout=12)
        if r.status_code == 404:
            return {"error": "404 — symbol not found on Screener.in"}
        if r.status_code != 200:
            return {"error": f"Screener returned HTTP {r.status_code}"}

        soup = BeautifulSoup(r.text, "lxml")

        # ── Top ratios bar ────────────────────────────────────────────────────
        ratios = soup.find("section", id="top-ratios")
        if ratios:
            for li in ratios.find_all("li"):
                label_el = li.find("span", class_="name")
                value_el = li.find("span", class_="number") or li.find("span", class_="value")
                if not label_el or not value_el:
                    continue
                label = label_el.get_text(strip=True).lower()
                value = _clean_num(value_el.get_text(strip=True))

                if "stock p/e" in label or label == "p/e":
                    data["pe_ratio"] = value
                elif "industry p/e" in label:
                    data["industry_pe"] = value
                elif "book value" in label:
                    data["book_value"] = value
                elif "face value" in label:
                    data["face_value"] = value
                elif "market cap" in label:
                    data["market_cap_cr"] = value
                elif "dividend yield" in label:
                    data["dividend_yield"] = value
                elif "roce" in label:
                    data["roce"] = value
                elif "roe" in label or "return on equity" in label:
                    data["roe"] = value
                elif "debt / equity" in label or "d/e" in label:
                    data["debt_to_equity"] = value
                elif "current ratio" in label:
                    data["current_ratio"] = value
                elif "eps" in label:
                    data["eps"] = value

        # ── Profit & Loss table — extract growth ──────────────────────────────
        data.update(_parse_pl_growth(soup))

        # ── Shareholding ──────────────────────────────────────────────────────
        data.update(_parse_shareholding(soup))

        if not data:
            return {"error": "Screener: no data parsed"}

        return data

    except Exception as e:
        return {"error": str(e)}


def _parse_pl_growth(soup: BeautifulSoup) -> dict:
    """Extracts YoY + 3Y revenue and profit growth from P&L table."""
    data = {}
    try:
        section = soup.find("section", id="profit-loss")
        if not section:
            return data
        table = section.find("table")
        if not table:
            return data

        for row in table.find_all("tr"):
            cols   = row.find_all("td")
            if not cols:
                continue
            label  = cols[0].get_text(strip=True).lower()
            values = [_clean_num(c.get_text(strip=True)) for c in cols[1:]]
            values = [v for v in values if v is not None]

            if not values:
                continue

            if "sales" in label or "revenue" in label:
                if len(values) >= 2 and values[-2] and values[-2] != 0:
                    data["revenue_growth_yoy"] = round(
                        ((values[-1] - values[-2]) / abs(values[-2])) * 100, 1)
                if len(values) >= 4 and values[-4] and values[-4] != 0:
                    data["sales_growth_3y"] = round(
                        ((values[-1] - values[-4]) / abs(values[-4])) * 100 / 3, 1)

            if ("net profit" in label or "profit after" in label) and "%" not in label:
                if len(values) >= 2 and values[-2] and values[-2] != 0:
                    data["profit_growth_yoy"] = round(
                        ((values[-1] - values[-2]) / abs(values[-2])) * 100, 1)
                if len(values) >= 4 and values[-4] and values[-4] != 0:
                    data["profit_growth_3y"] = round(
                        ((values[-1] - values[-4]) / abs(values[-4])) * 100 / 3, 1)
    except Exception:
        pass
    return data


def _parse_shareholding(soup: BeautifulSoup) -> dict:
    """Extracts latest promoter / FII / DII holdings."""
    data = {}
    try:
        section = soup.find("section", id="shareholding")
        if not section:
            return data
        table = section.find("table")
        if not table:
            return data

        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 2:
                continue
            label  = cols[0].get_text(strip=True).lower()
            values = [_clean_num(c.get_text(strip=True)) for c in cols[1:]]
            latest = next((v for v in reversed(values) if v is not None), None)

            if "promoter" in label:
                data["promoter_holding"] = latest
            elif "fii" in label or "foreign" in label:
                data["fii_holding"] = latest
            elif "dii" in label or "domestic" in label:
                data["dii_holding"] = latest
    except Exception:
        pass
    return data


# ─────────────────────────────────────────────────────────────
# yfinance fallback
# ─────────────────────────────────────────────────────────────

def _fetch_yfinance_fundamentals(ticker: str) -> dict:
    """
    Fallback fundamentals — yfinance removed (blocked on Render).
    Returns empty dict so Screener.in remains the only source.
    All fundamental data comes from Screener scraping above.
    """
    return {}


def _pct(val) -> float | None:
    """Convert 0.18 → 18.0 for percentage fields from yfinance."""
    if val is None:
        return None
    try:
        return round(float(val) * 100, 2)
    except Exception:
        return None
