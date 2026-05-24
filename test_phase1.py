"""
test_phase1.py
───────────────
Run this from the backend folder to verify Phase 1 is working.

Usage:
    python test_phase1.py               # tests RELIANCE
    python test_phase1.py HDFCBANK
    python test_phase1.py "Tata Motors"
    python test_phase1.py TCS investor
"""

import sys
from chatbot_data_aggregator import get_full_stock_data, get_market_context

# ── ANSI colours ──────────────────────────────────────────────
G  = "\033[92m"    # green
R  = "\033[91m"    # red
Y  = "\033[93m"    # yellow
C  = "\033[96m"    # cyan
W  = "\033[97m"    # white
DIM= "\033[2m"
RST= "\033[0m"


def bar(title: str):
    print(f"\n{C}{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}{RST}")


def run(symbol: str = "RELIANCE"):
    print(f"\n{W}Phase 1 test — {symbol}{RST}")

    # ── Market context ────────────────────────────────────────
    bar("Market Context")
    try:
        ctx = get_market_context()
        nc  = ctx.get("nifty50_change") or 0
        sc  = ctx.get("sensex_change")  or 0
        np_ = ctx.get("nifty50_price")
        sp_ = ctx.get("sensex_price")
        nc_col = G if nc >= 0 else R
        sc_col = G if sc >= 0 else R
        np_str = f"₹{np_:,.2f}" if np_ is not None else "N/A"
        sp_str = f"₹{sp_:,.2f}" if sp_ is not None else "N/A"
        print(f"  Nifty 50  : {W}{np_str}{RST}  {nc_col}{nc:+.2f}%{RST}")
        print(f"  Sensex    : {W}{sp_str}{RST}  {sc_col}{sc:+.2f}%{RST}")
        mood_col = G if "bull" in ctx["market_mood"] else R if "bear" in ctx["market_mood"] else Y
        print(f"  Mood      : {mood_col}{ctx['market_mood'].upper()}{RST}")
        ms = ctx["market_status"]
        status_col = G if ms.get("is_open") else Y
        print(f"  Market    : {status_col}{'OPEN' if ms.get('is_open') else 'CLOSED'} ({ms.get('reason','?')}){RST}")
    except Exception as e:
        print(f"  {R}ERROR: {e}{RST}")

    # ── Full stock data ───────────────────────────────────────
    bar(f"Fetching all data for: {symbol}")
    data = get_full_stock_data(symbol)

    # Price
    bar("Price Data")
    pd = data["price_data"]
    if pd.get("error"):
        print(f"  {R}ERROR: {pd['error']}{RST}")
    else:
        chg_col = G if (pd.get("change_pct") or 0) >= 0 else R
        print(f"  Company   : {W}{data['display_name']}{RST}")
        print(f"  Ticker    : {data['symbol']}")
        print(f"  Price     : {W}₹{pd['current_price']:,.2f}{RST}  "
              f"{chg_col}{pd['change']:+.2f} ({pd['change_pct']:+.2f}%){RST}")
        print(f"  Label     : {DIM}{pd['price_label']}{RST}")
        print(f"  O/H/L     : ₹{pd['open']:,.2f} / ₹{pd['high']:,.2f} / ₹{pd['low']:,.2f}")
        print(f"  52W H/L   : ₹{pd['week_52_high']:,.2f} / ₹{pd['week_52_low']:,.2f}")
        mc = pd.get("market_cap") or 0
        print(f"  Mkt Cap   : ₹{mc/1e7:,.0f} Cr" if mc else "  Mkt Cap   : N/A")
        print(f"  Volume    : {pd.get('volume', 0):,}")
        print(f"  Sector    : {pd.get('sector','N/A')}")

    # Fundamentals
    bar("Fundamentals")
    fd = data["fundamentals"]
    print(f"  Source       : {fd.get('source','?').upper()}")
    print(f"  P/E Ratio    : {fd.get('pe_ratio') or 'N/A'}")
    print(f"  P/B Ratio    : {fd.get('pb_ratio') or 'N/A'}")
    print(f"  RoE          : {fd.get('roe') or 'N/A'}%")
    print(f"  RoCE         : {fd.get('roce') or 'N/A'}%")
    print(f"  D/E          : {fd.get('debt_to_equity') or 'N/A'}")
    print(f"  EPS          : ₹{fd.get('eps') or 'N/A'}")
    rg = fd.get('revenue_growth_yoy')
    pg = fd.get('profit_growth_yoy')
    rg_col = G if rg and rg > 0 else R
    pg_col = G if pg and pg > 0 else R
    print(f"  Rev Growth   : {rg_col}{rg or 'N/A'}%{RST}")
    print(f"  Profit Growth: {pg_col}{pg or 'N/A'}%{RST}")
    print(f"  Promoter     : {fd.get('promoter_holding') or 'N/A'}%")
    print(f"  FII          : {fd.get('fii_holding') or 'N/A'}%")
    print(f"  Industry P/E : {fd.get('industry_pe') or 'N/A'}")
    print(f"  Div Yield    : {fd.get('dividend_yield') or 'N/A'}%")

    # OHLCV
    bar("OHLCV History")
    ohlcv = data["ohlcv"]
    if ohlcv.empty:
        print(f"  {R}No OHLCV data{RST}")
    else:
        print(f"  Rows        : {G}{len(ohlcv)} trading days{RST}")
        print(f"  Date range  : {ohlcv.index[0].strftime('%d %b %Y')} → "
              f"{ohlcv.index[-1].strftime('%d %b %Y')}")
        print(f"  Last close  : ₹{ohlcv['Close'].iloc[-1]:,.2f}")
        print(f"  EMA200 ok?  : {'Yes ✓' if len(ohlcv) >= 200 else f'No — only {len(ohlcv)} candles (need 200)'}")

    # News
    bar("News")
    nd = data["news"]
    print(f"  Total found  : {nd['total_fetched']}")
    print(f"  Company news : {len(nd['company_news'])}")
    print(f"  Macro news   : {len(nd['macro_news'])}")
    if nd["company_news"]:
        print(f"\n  Latest 3 company headlines:")
        for i, n in enumerate(nd["company_news"][:3], 1):
            tier_label = {1: "Full", 2: "Snippet", 3: "Headline"}.get(n.get("tier", 3), "?")
            print(f"  {i}. [{tier_label}] {n['title']}")
            print(f"     {DIM}{n['published']} | {n['source']}{RST}")

    # Errors / warnings
    if data["has_errors"]:
        bar("Warnings")
        print(f"  {Y}{data['error_summary']}{RST}")

    bar("Phase 1 COMPLETE ✓")
    print()


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    run(sym)