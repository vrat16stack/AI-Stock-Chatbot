"""
chatbot_fundamental_scorer.py
──────────────────────────────
Phase 2 — Fundamental Scoring Engine

Uses IDENTICAL logic to your stock_scout.py score_stock():
  - Same scoring weights (rev growth 20pts, earnings 20pts, ROE 12pts, D/E 8pts)
  - Same sector P/E averages for overvaluation flag (FLAW 2.5)
  - Same 5-factor target price formula
      tech_base × rsi_factor × macd_factor × ema_factor × fund_factor × val_factor
  - Same cap thresholds from decision_engine.py (Large/Mid/Small)

Extra for chatbot:
  - HOLD entry level suggestion (best price to enter if bot says HOLD)
  - trader_table / investor_table for UI display
  - investor_summary — plain English for investor mode
"""

from chatbot_technical import MIN_CANDLES   # reuse same file's constants


# ── Identical sector P/E from your stock_scout.py ────────────────────────────
SECTOR_PE: dict[str, int] = {
    'Technology':             25,
    'Financial Services':     18,
    'Healthcare':             30,
    'Consumer Defensive':     35,
    'Consumer Cyclical':      40,
    'Industrials':            28,
    'Energy':                 15,
    'Basic Materials':        12,
    'Real Estate':            35,
    'Utilities':              18,
    'Communication Services': 22,
}

# ── Identical cap thresholds from your decision_engine.py ────────────────────
LARGE_CAP = 20_000_00_00_000   # Rs. 20,000 Cr
MID_CAP   =  5_000_00_00_000   # Rs.  5,000 Cr

CAP_THRESHOLDS = {
    'Large Cap': {'stop_loss': -15, 'profit_target': 40},
    'Mid Cap':   {'stop_loss': -20, 'profit_target': 60},
    'Small Cap': {'stop_loss': -25, 'profit_target': 80},
}


def get_cap_category(market_cap: int | None) -> str:
    """Identical to decision_engine.py get_cap_category()."""
    if not market_cap:
        return 'Mid Cap'
    if market_cap >= LARGE_CAP:
        return 'Large Cap'
    elif market_cap >= MID_CAP:
        return 'Mid Cap'
    return 'Small Cap'


# ─────────────────────────────────────────────────────────────
# Main scoring function
# ─────────────────────────────────────────────────────────────

def score_fundamentals(
        fund_data:  dict,
        price_data: dict,
        tech_data:  dict) -> dict:
    """
    Scores fundamentals using same logic as stock_scout.py score_stock().

    fund_data   : from chatbot_fundamentals.py
    price_data  : from chatbot_price_fetcher.py
    tech_data   : from chatbot_technical.py

    Returns:
    {
        'score':             int (0-100),
        'score_breakdown':   list[str],
        'pe_flag':           str | None,
        'cap_category':      str,
        'cap_thresholds':    dict,
        'ai_target_price':   float,
        'upside_pct':        float,
        'target_basis':      str,
        'hold_entry_level':  float | None,
        'hold_entry_reason': str | None,
        'trader_table':      list[dict],
        'investor_table':    list[dict],
        'investor_summary':  str,
        'valuation_verdict': str,
        'sector_avg_pe':     int,
    }
    """
    score   = 0
    reasons = []

    current_price = price_data.get('current_price') or 0
    market_cap    = price_data.get('market_cap') or 0
    sector        = price_data.get('sector', 'N/A')

    cap_category = get_cap_category(market_cap)
    thresholds   = CAP_THRESHOLDS[cap_category]

    # Note: fund_data stores growth as plain % (e.g. 9.8 not 0.098)
    # because Screener.in returns it that way.
    # yfinance returns 0.098 — chatbot_fundamentals._pct() converts it.
    # So we read directly — no * 100 needed here.
    rev_growth    = fund_data.get('revenue_growth_yoy')    # already %
    profit_growth = fund_data.get('profit_growth_yoy')     # already %
    roe           = fund_data.get('roe')                   # already %
    dte           = fund_data.get('debt_to_equity')
    pe_ratio      = fund_data.get('pe_ratio')
    promoter      = fund_data.get('promoter_holding')

    sector_avg_pe = SECTOR_PE.get(sector, 25)
    pe_flag       = None
    val_verdict   = "Fair Value"

    # ── Revenue Growth — same weights as stock_scout.py ──────────────────────
    # stock_scout uses raw yfinance (0.25 = 25%), we use already-converted %
    if rev_growth is not None:
        if rev_growth > 25:
            score += 20
            reasons.append(f"Strong revenue growth: {rev_growth:.1f}%")
        elif rev_growth > 10:
            score += 12
            reasons.append(f"Good revenue growth: {rev_growth:.1f}%")
        elif rev_growth > 0:
            score += 5
            reasons.append(f"Moderate revenue growth: {rev_growth:.1f}%")
        else:
            score -= 5
            reasons.append(f"Declining revenue: {rev_growth:.1f}%")
    else:
        reasons.append("Revenue growth: Data unavailable")

    # ── Profit Growth — same weights ──────────────────────────────────────────
    if profit_growth is not None:
        if profit_growth > 25:
            score += 20
            reasons.append(f"Strong earnings growth: {profit_growth:.1f}%")
        elif profit_growth > 10:
            score += 10
            reasons.append(f"Good earnings growth: {profit_growth:.1f}%")
        elif profit_growth > 0:
            score += 4
            reasons.append(f"Moderate earnings growth: {profit_growth:.1f}%")
        else:
            score -= 5
            reasons.append(f"Declining profits: {profit_growth:.1f}%")
    else:
        reasons.append("Earnings growth: Data unavailable")

    # ── ROE — same weights as stock_scout.py ──────────────────────────────────
    # stock_scout: roe > 0.20 → 12pts, roe > 0.12 → 6pts
    # We use already-% form so: roe > 20 → 12pts, roe > 12 → 6pts
    if roe is not None:
        if roe > 20:
            score += 12
            reasons.append(f"High ROE: {roe:.1f}%")
        elif roe > 12:
            score += 6
            reasons.append(f"Decent ROE: {roe:.1f}%")
        else:
            reasons.append(f"Low ROE: {roe:.1f}%")

    # ── D/E — same weights ────────────────────────────────────────────────────
    if dte is not None:
        if dte < 0.3:
            score += 8
            reasons.append(f"Low debt (D/E: {dte:.2f}) — financially strong")
        elif dte < 1.0:
            score += 3
            reasons.append(f"Manageable debt (D/E: {dte:.2f})")
        elif dte > 1.5:
            score -= 5
            reasons.append(f"High debt (D/E: {dte:.2f}) — monitor closely")

    # ── Promoter holding (chatbot extra) ──────────────────────────────────────
    if promoter is not None:
        if promoter > 50:
            score += 5
            reasons.append(f"Strong promoter confidence: {promoter:.1f}% holding")
        elif promoter < 25:
            score -= 3
            reasons.append(f"Low promoter holding: {promoter:.1f}%")

    # ── P/E vs Sector — same logic as stock_scout.py FLAW 2.5 ────────────────
    if pe_ratio is not None and pe_ratio > 0:
        if pe_ratio > sector_avg_pe * 1.4:
            pe_flag     = (f"Expensive: P/E {pe_ratio:.1f} is 40%+ above "
                           f"{sector} sector avg ({sector_avg_pe})")
            val_verdict = "Overvalued"
        elif pe_ratio < sector_avg_pe * 0.7:
            score += 8
            reasons.append(f"Undervalued: P/E {pe_ratio:.1f} below sector avg "
                           f"({sector_avg_pe}) — potential upside")
            val_verdict = "Undervalued"
        else:
            reasons.append(f"Fair valuation: P/E {pe_ratio:.1f} "
                           f"(sector avg: {sector_avg_pe})")

    # ── 3-year consistency bonus ──────────────────────────────────────────────
    sales_3y = fund_data.get('sales_growth_3y')
    if sales_3y is not None and sales_3y > 15:
        score += 5
        reasons.append(f"Consistent 3-year sales growth: {sales_3y:.1f}% avg/yr")

    score = max(0, min(score, 100))

    # ── Target price — identical 5-factor formula from stock_scout.py ─────────
    target, upside, basis = _compute_target_price(
        current_price, tech_data, pe_ratio, sector_avg_pe,
        rev_growth, profit_growth
    )

    # ── HOLD entry level ──────────────────────────────────────────────────────
    hold_entry, hold_reason = _compute_hold_entry(current_price, tech_data)

    # ── Build tables ──────────────────────────────────────────────────────────
    trader_table   = _build_trader_table(
        fund_data, price_data, pe_ratio, sector_avg_pe,
        pe_flag, cap_category, val_verdict)
    investor_table = _build_investor_table(
        fund_data, price_data, pe_ratio, sector_avg_pe,
        val_verdict, cap_category)
    inv_summary    = _build_investor_summary(
        score, val_verdict, roe, dte, rev_growth, cap_category)

    return {
        'score':              score,
        'score_breakdown':    reasons,
        'pe_flag':            pe_flag,
        'cap_category':       cap_category,
        'cap_thresholds':     thresholds,
        'ai_target_price':    target,
        'upside_pct':         upside,
        'target_basis':       basis,
        'hold_entry_level':   hold_entry,
        'hold_entry_reason':  hold_reason,
        'trader_table':       trader_table,
        'investor_table':     investor_table,
        'investor_summary':   inv_summary,
        'valuation_verdict':  val_verdict,
        'sector_avg_pe':      sector_avg_pe,
    }


# ─────────────────────────────────────────────────────────────
# Target price — identical 5-factor formula from stock_scout.py
# ─────────────────────────────────────────────────────────────

def _compute_target_price(
        current_price: float,
        tech: dict,
        pe_ratio: float | None,
        sector_avg_pe: int,
        rev_growth: float | None,
        profit_growth: float | None) -> tuple[float, float, str]:
    """
    Identical formula to stock_scout.py score_stock() target calculation.
    tech_base × rsi_factor × macd_factor × ema_factor × fund_factor × val_factor
    """
    try:
        ema50    = tech.get('ema50')        or current_price
        ema200   = tech.get('ema200')       or current_price
        bb_upper = tech.get('bb_upper')     or current_price * 1.1
        adx      = tech.get('adx')          or 20
        rsi      = tech.get('rsi')          or 50
        macd_val = tech.get('macd')         or 0
        macd_sig = tech.get('macd_signal')  or 0

        # tech_base — identical
        momentum  = min(adx / 25, 1.5)
        tech_base = (ema50 * 1.15 * momentum + bb_upper) / 2

        # rsi_factor — identical
        rsi_factor  = 1.05 if rsi < 40 else 0.95 if rsi > 70 else 1.0

        # macd_factor — identical
        macd_factor = 1.03 if macd_val > macd_sig else 0.98

        # ema_factor — identical
        ema_factor  = 1.04 if ema200 and current_price > ema200 else 0.97

        # fund_factor — identical (note: our values are already %, scout uses ratio)
        # scout: rev_growth > 0.25 → +0.05 means >25%, same threshold
        fund_factor = 1.0
        if rev_growth is not None:
            if rev_growth > 25:   fund_factor += 0.05
            elif rev_growth > 10: fund_factor += 0.02
        if profit_growth is not None:
            if profit_growth > 25:   fund_factor += 0.05
            elif profit_growth > 10: fund_factor += 0.02
        fund_factor = min(fund_factor, 1.12)

        # val_factor — identical
        val_factor = 1.0
        if pe_ratio and pe_ratio > 0 and sector_avg_pe > 0:
            ratio = pe_ratio / sector_avg_pe
            if ratio < 0.7:   val_factor = 1.05
            elif ratio < 1.0: val_factor = 1.02
            elif ratio > 1.4: val_factor = 0.95

        raw_target = (tech_base * rsi_factor * macd_factor *
                      ema_factor * fund_factor * val_factor)
        target     = round(max(raw_target, current_price * 1.08), 2)
        upside     = round(((target - current_price) / current_price) * 100, 1)

        # Build basis string — same as scout
        factors = []
        if rsi_factor  > 1: factors.append("oversold RSI boost")
        if rsi_factor  < 1: factors.append("overbought RSI reduction")
        if macd_factor > 1: factors.append("bullish MACD momentum")
        if ema_factor  > 1: factors.append("above long-term EMA200")
        if fund_factor > 1: factors.append("strong fundamental growth")
        if val_factor  > 1: factors.append("undervalued vs sector")
        if val_factor  < 1: factors.append("overvalued vs sector (target reduced)")
        basis = ", ".join(factors) if factors else "technical resistance levels"

        return target, upside, basis

    except Exception:
        fallback = round(current_price * 1.12, 2)
        return fallback, 12.0, "technical levels (fallback)"


# ─────────────────────────────────────────────────────────────
# HOLD entry level
# ─────────────────────────────────────────────────────────────

def _compute_hold_entry(
        current_price: float,
        tech: dict) -> tuple[float | None, str | None]:
    """
    Suggests the best entry price when the recommendation is HOLD.
    Based on nearest support: BB lower → EMA50 → recent price support.
    """
    try:
        rsi      = tech.get('rsi')
        bb_lower = tech.get('bb_lower')
        ema50    = tech.get('ema50')
        supports = tech.get('support_levels', [])

        # Already oversold — enter now
        if rsi and rsi < 35:
            return (round(current_price, 2),
                    f"Stock is already oversold (RSI {rsi}) — "
                    f"current price is the entry level.")

        candidates = []
        labels     = []

        if bb_lower and bb_lower < current_price * 0.99:
            candidates.append(bb_lower)
            labels.append(f"lower Bollinger Band (₹{round(bb_lower,0):,.0f})")

        if ema50 and ema50 < current_price * 0.99:
            candidates.append(ema50)
            labels.append(f"EMA50 support (₹{round(ema50,0):,.0f})")

        if supports:
            candidates.append(supports[0])
            labels.append(f"recent price support (₹{round(supports[0],0):,.0f})")

        if candidates:
            best_idx = candidates.index(max(candidates))  # closest to current
            entry    = round(max(candidates), 2)
            reason   = (f"Wait for a dip to ₹{entry:,.2f}, which aligns with "
                        f"{labels[best_idx]}. This gives a better risk-reward entry.")
            return entry, reason

        # Fallback — 3-4% below current
        fallback = round(current_price * 0.96, 2)
        return (fallback,
                f"No strong support visible nearby. A 3-4% dip to ₹{fallback:,.2f} "
                f"would offer a safer entry with better risk-reward.")

    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────
# Table builders
# ─────────────────────────────────────────────────────────────

def _fmt(val, suffix="", dec=1) -> str:
    if val is None: return "N/A"
    return f"{round(val, dec)}{suffix}"


def _build_trader_table(
        fund, price, pe_ratio, sector_avg_pe,
        pe_flag, cap_category, val_verdict) -> list[dict]:
    """Full 15-row fundamental table for trader mode."""
    mc    = price.get('market_cap', 0) or 0
    mc_cr = round(mc / 1e7, 0) if mc else None

    rows = [
        {"metric":"Market Cap",
         "value": f"₹{mc_cr:,.0f} Cr" if mc_cr else "N/A",
         "verdict": cap_category},
        {"metric":"P/E Ratio",
         "value": _fmt(pe_ratio),
         "verdict": val_verdict},
        {"metric":"Industry P/E",
         "value": str(sector_avg_pe),
         "verdict": "Benchmark"},
        {"metric":"P/B Ratio",
         "value": _fmt(fund.get('pb_ratio')),
         "verdict": "Check" if (fund.get('pb_ratio') or 0) > 5 else "OK"},
        {"metric":"RoE",
         "value": _fmt(fund.get('roe'), "%"),
         "verdict": "Strong" if (fund.get('roe') or 0) > 20
                    else "Decent" if (fund.get('roe') or 0) > 12 else "Weak"},
        {"metric":"RoCE",
         "value": _fmt(fund.get('roce'), "%"),
         "verdict": "Strong" if (fund.get('roce') or 0) > 20 else "Check"},
        {"metric":"Debt / Equity",
         "value": _fmt(fund.get('debt_to_equity')),
         "verdict": ("Low" if (fund.get('debt_to_equity') or 99) < 0.3
                     else "High" if (fund.get('debt_to_equity') or 0) > 1.5
                     else "Moderate")},
        {"metric":"EPS",
         "value": _fmt(fund.get('eps')),
         "verdict": "Positive" if (fund.get('eps') or 0) > 0 else "Negative"},
        {"metric":"Revenue Growth (YoY)",
         "value": _fmt(fund.get('revenue_growth_yoy'), "%"),
         "verdict": ("Strong" if (fund.get('revenue_growth_yoy') or 0) > 20
                     else "Good" if (fund.get('revenue_growth_yoy') or 0) > 10
                     else "Weak")},
        {"metric":"Profit Growth (YoY)",
         "value": _fmt(fund.get('profit_growth_yoy'), "%"),
         "verdict": ("Strong" if (fund.get('profit_growth_yoy') or 0) > 20
                     else "Good" if (fund.get('profit_growth_yoy') or 0) > 10
                     else "Weak")},
        {"metric":"3Y Sales Growth (avg/yr)",
         "value": _fmt(fund.get('sales_growth_3y'), "%"),
         "verdict": "Strong" if (fund.get('sales_growth_3y') or 0) > 15 else "Moderate"},
        {"metric":"Promoter Holding",
         "value": _fmt(fund.get('promoter_holding'), "%"),
         "verdict": "High" if (fund.get('promoter_holding') or 0) >= 50 else "Low"},
        {"metric":"FII Holding",
         "value": _fmt(fund.get('fii_holding'), "%"),
         "verdict": ("High FII interest"
                     if (fund.get('fii_holding') or 0) > 20 else "Moderate")},
        {"metric":"DII Holding",
         "value": _fmt(fund.get('dii_holding'), "%"),
         "verdict": "Institutional support" if (fund.get('dii_holding') or 0) > 10 else "Low"},
        {"metric":"Dividend Yield",
         "value": _fmt(fund.get('dividend_yield'), "%"),
         "verdict": ("Income stock" if (fund.get('dividend_yield') or 0) > 1
                     else "Growth stock")},
    ]

    if pe_flag:
        rows.append({"metric":"⚠ Valuation Flag",
                     "value":"WARNING", "verdict": pe_flag})

    return rows


def _build_investor_table(
        fund, price, pe_ratio, sector_avg_pe,
        val_verdict, cap_category) -> list[dict]:
    """Simplified 6-row table for investor mode with plain English."""
    mc    = price.get('market_cap', 0) or 0
    mc_cr = round(mc / 1e7, 0) if mc else None

    rg = fund.get('revenue_growth_yoy')
    pg = fund.get('profit_growth_yoy')
    ro = fund.get('roe')
    dt = fund.get('debt_to_equity')

    return [
        {"metric":"Company size",
         "value": f"₹{mc_cr:,.0f} Cr" if mc_cr else "N/A",
         "verdict": cap_category,
         "plain": f"This is a {cap_category} company"},
        {"metric":"Is it growing revenue?",
         "value": _fmt(rg, "% YoY"),
         "verdict": "Yes" if (rg or 0) > 10 else "Slow",
         "plain": "Revenue is growing well" if (rg or 0) > 10 else "Revenue growth is slow"},
        {"metric":"Is it profitable?",
         "value": _fmt(pg, "% profit growth"),
         "verdict": "Growing" if (pg or 0) > 0 else "Declining",
         "plain": "Profits are growing" if (pg or 0) > 0 else "Profits have declined"},
        {"metric":"Is it efficient?",
         "value": _fmt(ro, "% RoE"),
         "verdict": "Efficient" if (ro or 0) > 15 else "Average",
         "plain": ("Company uses shareholder money efficiently"
                   if (ro or 0) > 15 else "Efficiency is average")},
        {"metric":"Is it in debt?",
         "value": _fmt(dt, " D/E"),
         "verdict": "Low debt" if (dt or 99) < 0.5 else "High debt",
         "plain": ("Low debt — financially stable"
                   if (dt or 99) < 0.5 else "Carries significant debt")},
        {"metric":"Is it cheap?",
         "value": _fmt(pe_ratio, " P/E"),
         "verdict": val_verdict,
         "plain": (f"Fairly priced vs its sector"
                   if val_verdict == "Fair Value"
                   else val_verdict)},
    ]


def _build_investor_summary(
        score: int, val_verdict: str,
        roe: float | None, dte: float | None,
        rev_growth: float | None,
        cap_category: str) -> str:

    parts = []
    if score >= 60:
        parts.append(f"Fundamentally, this looks like a solid {cap_category} company.")
    elif score >= 35:
        parts.append(f"This {cap_category} company has mixed fundamentals — "
                     f"some strengths, some areas to watch.")
    else:
        parts.append(f"The fundamentals of this {cap_category} company "
                     f"are relatively weak right now.")

    if rev_growth and rev_growth > 15:
        parts.append(f"Revenue is growing at {rev_growth:.0f}% — that's healthy.")
    elif rev_growth and rev_growth < 0:
        parts.append("Revenue has been declining, worth monitoring.")

    if val_verdict == "Undervalued":
        parts.append("The stock appears undervalued compared to similar sector peers.")
    elif val_verdict == "Overvalued":
        parts.append("The stock is priced at a premium — you're paying extra for it.")

    return " ".join(parts)