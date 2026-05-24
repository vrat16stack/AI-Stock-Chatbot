"""
chatbot_sentiment.py
─────────────────────
Phase 2 — Groq AI Sentiment & Recommendation Engine

Same prompt structure as your existing news_sentiment.py but adapted
for QUERY mode (user asking about a stock they want to buy, not one
they already hold).

Two prompt variants:
  TRADER   → full technical detail, all indicators, entry + SL + target
  INVESTOR → simple language, no jargon, plain explanations

Same output field parsing as your existing analyze_sentiment_with_groq().
Same tiered news confidence labels (Full Article / Snippet / Headline).
"""

import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL", "llama3-70b-8192")

# Tier labels — same as your news_sentiment.py
TIER_LABELS = {
    1: "[Full Article]",
    2: "[Snippet]",
    3: "[Headline Only — low confidence]",
}


def _get_client() -> Groq:
    if not GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to your backend/.env file.")
    return Groq(api_key=GROQ_API_KEY)


# ─────────────────────────────────────────────────────────────
# News formatter — same as your news_sentiment.py
# ─────────────────────────────────────────────────────────────

def _format_news(news_data: dict) -> str:
    """
    Formats news into the same text block used in your existing
    analyze_sentiment_with_groq() prompt.
    """
    if not news_data or news_data.get("total_fetched", 0) == 0:
        return "No recent news found."

    lines = []

    if news_data.get("company_news"):
        lines.append("=== COMPANY NEWS (last 14 days) ===")
        for a in news_data["company_news"]:
            label   = TIER_LABELS.get(a.get("tier", 3), "[Headline]")
            content = a.get("content") or a["title"]
            lines.append(
                f"- {label} {a['title']} ({a['published']}) | {a['source']}\n"
                f"  {content[:300]}"
            )

    if news_data.get("macro_news"):
        lines.append("\n=== INDIA MACRO / MARKET NEWS ===")
        for a in news_data["macro_news"]:
            lines.append(f"- {a['title']} ({a['published']}) | {a['source']}")

    return "\n".join(lines) if lines else "No recent news available."


# ─────────────────────────────────────────────────────────────
# Trader prompt — full detail
# ─────────────────────────────────────────────────────────────

def _build_trader_prompt(
        stock_name: str, symbol: str,
        current_price: float, price_label: str,
        sector: str, week_high: float, week_low: float,
        tech: dict, fund: dict, fund_score: dict,
        news_text: str,
        fg_score: int, fg_rating: str, mkt_mood: str) -> str:

    rsi      = tech.get('rsi',          'N/A')
    macd_val = tech.get('macd',         'N/A')
    macd_sig = tech.get('macd_signal',  'N/A')
    adx      = tech.get('adx',          'N/A')
    stoch_k  = tech.get('stoch_k',      'N/A')
    ema50    = tech.get('ema50',         'N/A')
    ema200   = tech.get('ema200',        'N/A')
    bb_upper = tech.get('bb_upper',     'N/A')
    bb_lower = tech.get('bb_lower',     'N/A')
    bull_pct = tech.get('bull_pct',      50)
    tech_sig = tech.get('technical_signal', 'NEUTRAL')
    insuff   = tech.get('insufficient_indicators', [])
    insuff_note = (f"\nNote — Skipped (insufficient data): {', '.join(insuff)}"
                   if insuff else "")
    tech_notes  = '\n'.join([f"  - {n}"
                             for n in tech.get('technical_notes', [])])

    pe_ratio = fund.get('pe_ratio',    'N/A')
    pb_ratio = fund.get('pb_ratio',    'N/A')
    roe      = fund.get('roe',         'N/A')
    dte      = fund.get('debt_to_equity', 'N/A')
    rev_g    = fund.get('revenue_growth_yoy',  'N/A')
    profit_g = fund.get('profit_growth_yoy',   'N/A')
    promoter = fund.get('promoter_holding',    'N/A')
    fund_src = fund.get('source', 'N/A')

    cap_cat     = fund_score.get('cap_category',    'Mid Cap')
    fund_scr    = fund_score.get('score',            0)
    val_verdict = fund_score.get('valuation_verdict','N/A')
    ai_target   = fund_score.get('ai_target_price', 'N/A')
    upside      = fund_score.get('upside_pct',       'N/A')

    return f"""You are an expert Indian stock market analyst. A TRADER is asking
whether to BUY {stock_name} (NSE: {symbol}).

Analyse ALL data below comprehensively and give a precise, actionable call.

STOCK SNAPSHOT:
- Stock       : {stock_name} ({symbol}.NS) | Sector: {sector} | {cap_cat}
- {price_label}: ₹{current_price:,.2f}
- 52W High    : ₹{week_high:,.2f} | 52W Low: ₹{week_low:,.2f}

MARKET CONTEXT:
- Market mood       : {mkt_mood}
- Fear & Greed Index: {fg_score} ({fg_rating})

TECHNICAL INDICATORS:{insuff_note}
- RSI (14)          : {rsi}
- MACD              : {macd_val} vs Signal {macd_sig}
- ADX               : {adx} (>25 = strong trend)
- Stochastic %K     : {stoch_k}
- EMA50             : {ema50} | EMA200: {ema200}
- Bollinger Bands   : Upper {bb_upper} / Lower {bb_lower}
- Bull Score        : {bull_pct}% | Signal: {tech_sig}
Technical notes:
{tech_notes}

FUNDAMENTALS (source: {fund_src}) — Fundamental Score: {fund_scr}/100:
- P/E Ratio         : {pe_ratio} | P/B: {pb_ratio}
- ROE               : {roe}% | Debt/Equity: {dte}
- Revenue Growth    : {rev_g}% (YoY)
- Profit Growth     : {profit_g}% (YoY)
- Promoter Holding  : {promoter}%
- Valuation         : {val_verdict} vs sector
- Pre-calc target   : ₹{ai_target} (+{upside}% upside)

RECENT NEWS:
{news_text}

Respond in EXACTLY this format — no extra text, no preamble:
NEWS_SENTIMENT: [POSITIVE/NEGATIVE/NEUTRAL]
OVERALL_SENTIMENT: [BULLISH/BEARISH/NEUTRAL]
RECOMMENDATION: [BUY/HOLD/SELL]
CONFIDENCE: [HIGH/MEDIUM/LOW]
RECOMMENDATION_DETAIL: [3-4 sentences. Be specific — mention key technical levels, fundamental strengths/weaknesses, and news impact together.]
RISK_FACTORS: [2 key risks, comma separated]
TARGET_PRICE: [realistic target in ₹ — just a number e.g. 1850.00]
STOP_LOSS: [stop loss price in ₹ — just a number e.g. 1200.00]
ENTRY_LEVEL: [if BUY write CURRENT. If HOLD write the better entry price as a number. If SELL write AVOID.]
ENTRY_REASON: [one sentence — why that entry level or why to avoid]"""


# ─────────────────────────────────────────────────────────────
# Investor prompt — simple language
# ─────────────────────────────────────────────────────────────

def _build_investor_prompt(
        stock_name: str, symbol: str,
        current_price: float, price_label: str,
        sector: str, week_high: float, week_low: float,
        tech: dict, fund: dict, fund_score: dict,
        news_text: str,
        fg_rating: str, mkt_mood: str) -> str:

    rsi      = tech.get('rsi',     'N/A')
    ema200   = tech.get('ema200',  'N/A')
    bb_lower = tech.get('bb_lower','N/A')
    bull_pct = tech.get('bull_pct', 50)
    tech_sig = tech.get('technical_signal', 'NEUTRAL')
    insuff   = tech.get('insufficient_indicators', [])
    insuff_note = (f"\nNote — Skipped (insufficient data): {', '.join(insuff)}"
                   if insuff else "")

    ema200_pos = "above" if (ema200 != 'N/A' and ema200
                             and current_price > float(str(ema200))
                             ) else "below"

    rev_g    = fund.get('revenue_growth_yoy', 'N/A')
    profit_g = fund.get('profit_growth_yoy',  'N/A')
    roe      = fund.get('roe',                'N/A')
    dte      = fund.get('debt_to_equity',     'N/A')
    promoter = fund.get('promoter_holding',   'N/A')
    pe_ratio = fund.get('pe_ratio',           'N/A')

    cap_cat     = fund_score.get('cap_category',    'Mid Cap')
    val_verdict = fund_score.get('valuation_verdict','N/A')
    fund_scr    = fund_score.get('score', 0)

    return f"""You are a friendly Indian stock market advisor explaining to an INVESTOR
— someone who understands stocks but doesn't track them daily.

The investor wants to know whether {stock_name} (NSE: {symbol}) is worth buying
as a long-term holding. Use simple, clear language. Avoid heavy jargon.
Where you use a technical term, briefly explain what it means in brackets.

STOCK: {stock_name} ({symbol}) | Sector: {sector} | {cap_cat}
Price : ₹{current_price:,.2f} ({price_label})
52W range: ₹{week_low:,.2f} – ₹{week_high:,.2f}
Market mood: {mkt_mood} | Fear & Greed: {fg_rating}

SIMPLIFIED CHART PICTURE:{insuff_note}
- RSI (momentum indicator): {rsi}  ← below 35 = oversold bargain; above 65 = getting expensive
- Chart signal: {tech_sig} ({bull_pct}% of indicators positive)
- Long-term trend (EMA200): stock is {ema200_pos} its long-term average
- Lower support zone: around ₹{bb_lower}
- Fundamental score: {fund_scr}/100

COMPANY HEALTH:
- Revenue growing at : {rev_g}% per year
- Profits growing at : {profit_g}% per year
- Return on Equity   : {roe}%  ← how well it uses shareholder money
- Debt level (D/E)   : {dte}   ← below 0.5 = low debt = good
- Promoter holding   : {promoter}%  ← how much the founders own
- P/E Ratio          : {pe_ratio}   ← how expensive vs peers
- Valuation          : {val_verdict} compared to sector

RECENT NEWS:
{news_text}

Respond in EXACTLY this format — no extra text, no preamble:
NEWS_SENTIMENT: [POSITIVE/NEGATIVE/NEUTRAL]
OVERALL_SENTIMENT: [BULLISH/BEARISH/NEUTRAL]
RECOMMENDATION: [BUY/HOLD/SELL]
CONFIDENCE: [HIGH/MEDIUM/LOW]
RECOMMENDATION_DETAIL: [3 sentences in simple language. What does the company do well? What does the chart say? What should the investor watch out for? No jargon — if you must use a term, explain it briefly.]
RISK_FACTORS: [2 risks explained in plain English, comma separated]
TARGET_PRICE: [a realistic long-term target price in ₹ — just a number]
STOP_LOSS: [a safety exit price in ₹ — just a number]
ENTRY_LEVEL: [if BUY write CURRENT. If HOLD write a better entry price as a number. If SELL write AVOID.]
ENTRY_REASON: [one sentence in plain language — why that price or why to avoid]"""


# ─────────────────────────────────────────────────────────────
# Response parser — same field-by-field logic as your file
# ─────────────────────────────────────────────────────────────

def _parse_response(text: str, persona: str) -> dict:
    """Identical parsing logic to your analyze_sentiment_with_groq()."""
    result = {
        'news_sentiment':        'NEUTRAL',
        'overall_sentiment':     'NEUTRAL',
        'recommendation':        'HOLD',
        'confidence':            'LOW',
        'recommendation_detail': 'Analysis completed.',
        'risk_factors':          'N/A',
        'target_price':          None,
        'stop_loss':             None,
        'entry_level':           None,
        'entry_reason':          None,
        'raw_response':          text,
        'persona':               persona,
        'error':                 None,
    }

    for line in text.split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue
        key, _, val = line.partition(':')
        key = key.strip().upper()
        val = val.strip()

        if   key == 'NEWS_SENTIMENT':        result['news_sentiment']        = val
        elif key == 'OVERALL_SENTIMENT':     result['overall_sentiment']     = val
        elif key == 'RECOMMENDATION':        result['recommendation']        = val
        elif key == 'CONFIDENCE':            result['confidence']            = val
        elif key == 'RECOMMENDATION_DETAIL': result['recommendation_detail'] = val
        elif key == 'RISK_FACTORS':          result['risk_factors']          = val
        elif key == 'ENTRY_REASON':          result['entry_reason']          = val
        elif key == 'TARGET_PRICE':
            try:
                result['target_price'] = float(
                    val.replace('₹','').replace(',','').strip())
            except Exception:
                pass
        elif key == 'STOP_LOSS':
            try:
                result['stop_loss'] = float(
                    val.replace('₹','').replace(',','').strip())
            except Exception:
                pass
        elif key == 'ENTRY_LEVEL':
            v = val.upper().strip()
            if v in ('CURRENT', 'AVOID', 'N/A', 'NOW'):
                result['entry_level'] = None
            else:
                try:
                    result['entry_level'] = float(
                        val.replace('₹','').replace(',','').strip())
                except Exception:
                    result['entry_level'] = None

    return result


def _fallback_result(error_msg: str, persona: str) -> dict:
    return {
        'news_sentiment':        'NEUTRAL',
        'overall_sentiment':     'NEUTRAL',
        'recommendation':        'HOLD',
        'confidence':            'LOW',
        'recommendation_detail': f'AI analysis unavailable: {error_msg}',
        'risk_factors':          'N/A',
        'target_price':          None,
        'stop_loss':             None,
        'entry_level':           None,
        'entry_reason':          None,
        'raw_response':          '',
        'persona':               persona,
        'error':                 error_msg,
    }


# ─────────────────────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────────────────────

def run_sentiment_analysis(
        stock_name:     str,
        symbol:         str,
        news_data:      dict,
        technical:      dict,
        fundamentals:   dict,
        fund_score:     dict,
        price_data:     dict,
        persona:        str  = "trader",
        market_context: dict = None) -> dict:
    """
    Calls Groq with persona-specific prompt.
    Returns parsed sentiment + recommendation dict.

    persona = 'trader'   → full detail prompt
    persona = 'investor' → simple language prompt
    """
    try:
        client = _get_client()
    except ValueError as e:
        return _fallback_result(str(e), persona)

    mkt    = market_context or {}
    fg_score  = mkt.get('fear_greed_score',  50)
    fg_rating = mkt.get('fear_greed_rating', 'Neutral')
    mkt_mood  = mkt.get('market_mood',       'sideways/neutral')

    current_price = price_data.get('current_price', 0) or 0
    price_label   = price_data.get('price_label', 'Current price')
    sector        = price_data.get('sector', 'N/A')
    week_high     = price_data.get('week_52_high', 0) or 0
    week_low      = price_data.get('week_52_low',  0) or 0

    news_text = _format_news(news_data)

    # ── Build prompt based on persona ─────────────────────────────────────────
    if persona == "investor":
        prompt = _build_investor_prompt(
            stock_name, symbol, current_price, price_label,
            sector, week_high, week_low,
            technical, fundamentals, fund_score,
            news_text, fg_rating, mkt_mood)
    else:
        prompt = _build_trader_prompt(
            stock_name, symbol, current_price, price_label,
            sector, week_high, week_low,
            technical, fundamentals, fund_score,
            news_text, fg_score, fg_rating, mkt_mood)

    # ── Call Groq — same pattern as your news_sentiment.py ────────────────────
    try:
        response = client.chat.completions.create(
            model    = GROQ_MODEL,
            messages = [{"role": "user", "content": prompt}],
            max_tokens  = 600,
            temperature = 0.2,
        )
        text = response.choices[0].message.content.strip()
        return _parse_response(text, persona)

    except Exception as e:
        print(f"[sentiment] Groq error: {e}")
        return _fallback_result(f"Groq API error: {e}", persona)
