"""
test_phase2.py
───────────────
Full Phase 2 pipeline test — runs everything end to end.

Usage:
    python test_phase2.py                      # RELIANCE, trader mode
    python test_phase2.py HDFCBANK             # trader mode
    python test_phase2.py TATAMOTORS investor  # investor mode
    python test_phase2.py TCS trader
"""

import sys
from chatbot_analysis_engine import analyse_stock

# ── ANSI colours ──────────────────────────────────────────────
G   = "\033[92m"
R   = "\033[91m"
Y   = "\033[93m"
C   = "\033[96m"
W   = "\033[97m"
DIM = "\033[2m"
RST = "\033[0m"


def bar(title: str, color: str = C):
    print(f"\n{color}{'─'*62}")
    print(f"  {title}")
    print(f"{'─'*62}{RST}")


def sig_color(sig: str) -> str:
    return G if sig == 'BULLISH' else R if sig == 'BEARISH' else Y


def run(symbol: str, persona: str = "trader"):
    print(f"\n{W}Phase 2 full test — {symbol} ({persona.upper()} mode){RST}")
    print(f"{DIM}Running full pipeline: data fetch → technical → "
          f"fundamental → Groq AI...{RST}\n")

    result = analyse_stock(symbol, persona)

    # ── Error check ───────────────────────────────────────────
    if result.get('status') == 'error':
        bar("ERROR", R)
        print(f"  {R}{result.get('error', 'Unknown error')}{RST}")
        return

    # ── Price ─────────────────────────────────────────────────
    bar("Price Data")
    p   = result['price']
    chg = p.get('change_pct') or 0
    cc  = G if chg >= 0 else R
    print(f"  Company   : {W}{result['display_name']}{RST}")
    print(f"  Ticker    : {result['symbol']}")
    print(f"  Price     : {W}₹{p['current']:,.2f}{RST}  "
          f"{cc}{p.get('change',0):+.2f} ({chg:+.2f}%){RST}")
    print(f"  Label     : {DIM}{p.get('label','')}{RST}")
    print(f"  52W H/L   : ₹{p.get('week_52_high',0):,.2f} / "
          f"₹{p.get('week_52_low',0):,.2f}")
    mc = p.get('market_cap', 0) or 0
    print(f"  Mkt Cap   : ₹{mc/1e7:,.0f} Cr" if mc else
          "  Mkt Cap   : N/A")
    print(f"  Sector    : {p.get('sector','N/A')}")

    # ── Technical ─────────────────────────────────────────────
    bar("Technical Analysis")
    t   = result['technical']
    sc  = sig_color(t['signal'])
    print(f"  Signal    : {sc}{t['signal']}{RST} "
          f"({t['bull_pct']}% bullish | "
          f"Bullish score: {t['bullish_score']} | "
          f"Bearish score: {t['bearish_score']})")
    print(f"  Candles   : {t['candles']} trading days")
    if t['insufficient']:
        print(f"  Skipped   : {Y}{', '.join(t['insufficient'])}{RST}")

    if persona == 'trader':
        print(f"\n  {'Indicator':<26} {'Value':<28} {'Signal':<10} Interpretation")
        print(f"  {'─'*90}")
        for row in t['table']:
            sc2 = sig_color(row.get('signal','NEUTRAL'))
            print(f"  {row['indicator']:<26} "
                  f"{str(row['value']):<28} "
                  f"{sc2}{row.get('signal',''):<10}{RST} "
                  f"{row.get('interpretation','')}")
    else:
        print(f"\n  {t.get('investor_summary','')}")

    if t['support']:
        s_str = ' | '.join([f"₹{int(s):,}" for s in t['support']])
        print(f"\n  Support   : {G}{s_str}{RST}")
    if t['resistance']:
        r_str = ' | '.join([f"₹{int(r):,}" for r in t['resistance']])
        print(f"  Resistance: {R}{r_str}{RST}")

    # ── Fundamental ───────────────────────────────────────────
    bar("Fundamental Analysis")
    f = result['fundamental']
    score_c = G if (f['score'] or 0) >= 60 else Y if (f['score'] or 0) >= 35 else R
    print(f"  Score     : {score_c}{f['score']}/100{RST} | "
          f"Valuation: {f.get('valuation','N/A')}")

    if persona == 'trader':
        print(f"\n  {'Metric':<28} {'Value':<20} Verdict")
        print(f"  {'─'*70}")
        for row in f['table']:
            print(f"  {row['metric']:<28} "
                  f"{str(row['value']):<20} "
                  f"{row.get('verdict','')}")
    else:
        print(f"\n  {'Metric':<25} {'Value':<22} {'Verdict':<16} Plain English")
        print(f"  {'─'*85}")
        for row in f['table']:
            print(f"  {row['metric']:<25} "
                  f"{str(row['value']):<22} "
                  f"{row.get('verdict',''):<16} "
                  f"{row.get('plain','')}")
        print(f"\n  {f.get('investor_summary','')}")

    if f.get('pe_flag'):
        print(f"\n  {Y}⚠ {f['pe_flag']}{RST}")

    # ── News ──────────────────────────────────────────────────
    bar("News & Sentiment")
    n    = result['news']
    nsc  = G if n['sentiment'] == 'POSITIVE' else \
           R if n['sentiment'] == 'NEGATIVE' else Y
    print(f"  News sentiment  : {nsc}{n['sentiment']}{RST}")
    print(f"  AI sentiment    : {sig_color(n['overall'])}{n['overall']}{RST}")
    print(f"  Articles found  : {n['total_articles']}")
    if n['company_headlines']:
        print(f"\n  Company headlines:")
        for h in n['company_headlines'][:3]:
            print(f"    • {h}")

    # ── Market context ────────────────────────────────────────
    bar("Market Context")
    m  = result['market']
    nc = m.get('nifty_change') or 0
    print(f"  Nifty 50   : "
          f"{'₹'+f\"{m['nifty50']:,.2f}\" if m.get('nifty50') else 'N/A'}"
          f"  {G if nc>=0 else R}{nc:+.2f}%{RST}")
    print(f"  Market mood: {m.get('mood','N/A').upper()}")
    fg = m.get('fear_greed_score') or 50
    fg_c = G if fg <= 45 else R if fg >= 75 else Y
    print(f"  Fear&Greed : {fg_c}{fg} — {m.get('fear_greed_rating','N/A')}"
          f" {m.get('fear_greed_emoji','')}{RST}")
    print(f"  Advice     : {DIM}{m.get('fear_greed_advice','')}{RST}")

    # ── Final verdict ──────────────────────────────────────────
    v   = result['verdict']
    vc  = G if v.get('decision', v.get('verdict','HOLD')) == 'BUY' else R if v.get('decision', v.get('verdict','HOLD')) == 'SELL' else Y
    bar(f"FINAL VERDICT — {v.get('decision', v.get('verdict','HOLD'))}", vc)
    print(f"\n  {vc}{v.get('decision', v.get('verdict','HOLD'))}{RST}  "
          f"Confidence: {v['confidence']}  |  "
          f"Signal: {sig_color(v['combined_signal'])}"
          f"{v['combined_signal']}{RST}  |  "
          f"Cap: {v['cap_category']}")

    if v.get('target_price'):
        print(f"\n  Target    : {G}₹{v['target_price']:,.2f}{RST}  "
              f"(+{v.get('upside_pct','?')}% upside)")
    if v.get('stop_loss'):
        print(f"  Stop Loss : {R}₹{v['stop_loss']:,.2f}{RST}")
    if v.get('risk_reward'):
        print(f"  R:R Ratio : 1 : {v['risk_reward']}")

    if v.get('entry_level') and v.get('decision', v.get('verdict','HOLD')) == 'HOLD':
        print(f"\n  {Y}Entry Level : ₹{v['entry_level']:,.2f}{RST}")
        print(f"  Entry Note  : {v.get('entry_reason','')}")

    print(f"\n  {DIM}{v.get('detail','')}{RST}")

    if v.get('risk_factors'):
        print(f"\n  {Y}⚠ Risks: {v['risk_factors']}{RST}")

    if result['meta'].get('has_errors'):
        bar("Data Warnings", Y)
        print(f"  {Y}{result['meta']['error_summary']}{RST}")

    bar("Phase 2 COMPLETE ✓", G)
    print()


if __name__ == "__main__":
    sym     = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    persona = sys.argv[2] if len(sys.argv) > 2 else "trader"
    run(sym, persona)