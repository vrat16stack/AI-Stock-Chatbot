"""
chatbot_analysis_engine.py
───────────────────────────
Phase 2 — Master Analysis Orchestrator

Single entry point that the API (Phase 3) will call.
Runs the full pipeline in order:
  1. Phase 1: fetch price + fundamentals + news + OHLCV
  2. Phase 2a: technical analysis
  3. Phase 2b: fundamental scoring
  4. Phase 2c: fear & greed + market context
  5. Phase 2d: Groq sentiment + recommendation
  6. Build final unified output dict

Decision logic mirrors your decision_engine.py combined signal:
  BULLISH if tech OR sentiment = BULLISH
  BEARISH if BOTH tech AND sentiment = BEARISH
  else NEUTRAL
"""

import sys
import os
import concurrent.futures

# Phase 1 imports
from chatbot_data_aggregator   import get_full_stock_data, get_market_context
from chatbot_technical         import run_technical_analysis
from chatbot_fundamental_scorer import score_fundamentals
from chatbot_sentiment         import run_sentiment_analysis

# Reuse your existing fear_greed.py
# Try to import from same folder first, then parent
try:
    from fear_greed import get_fear_greed
except ImportError:
    def get_fear_greed() -> dict:
        """Inline fallback — calls alternative.me API directly."""
        import urllib.request, json
        try:
            url = "https://api.alternative.me/fng/?limit=1"
            req = urllib.request.Request(url,
                headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            latest = data["data"][0]
            score  = int(latest["value"])
            rating = latest["value_classification"].title()

            if score <= 25:
                advice = "Extreme Fear — historically a good time to buy quality stocks."
            elif score <= 45:
                advice = "Fear in market — cautious buying opportunities may exist."
            elif score <= 55:
                advice = "Neutral market — normal conditions."
            elif score <= 75:
                advice = "Greed building — be selective, avoid chasing rallies."
            else:
                advice = "Extreme Greed — consider booking profits on stocks near targets."

            return {"score": score, "rating": rating, "advice": advice,
                    "emoji": "😐", "color": "#FF9800"}
        except Exception:
            return {"score": 50, "rating": "Neutral",
                    "advice": "Market mood data unavailable.",
                    "emoji": "😐", "color": "#FF9800"}


# ─────────────────────────────────────────────────────────────
# Main analysis function
# ─────────────────────────────────────────────────────────────

def analyse_stock(symbol: str, persona: str = "trader") -> dict:
    """
    Full analysis pipeline for any NSE stock.

    symbol  : any NSE symbol or company name (e.g. 'RELIANCE', 'Tata Motors')
    persona : 'trader' | 'investor'

    Returns unified dict ready for the API and frontend.
    """

    # ── Step 1: Fetch all raw data (Phase 1) ──────────────────────────────────
    raw = get_full_stock_data(symbol)
    price_data = raw['price_data']

    if price_data.get('error'):
        return {
            'status':  'error',
            'symbol':  symbol,
            'error':   price_data['error'],
            'persona': persona,
        }

    if not price_data.get('current_price'):
        return {
            'status':  'error',
            'symbol':  symbol,
            'error':   f"No price data available for '{symbol}'.",
            'persona': persona,
        }

    # ── Step 2: Market context + Fear & Greed in parallel ─────────────────────
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        mkt_f = ex.submit(get_market_context)
        fg_f  = ex.submit(get_fear_greed)

    market_ctx = mkt_f.result()
    fear_greed = fg_f.result()

    market_ctx['fear_greed_score']  = fear_greed.get('score',  50)
    market_ctx['fear_greed_rating'] = fear_greed.get('rating', 'Neutral')
    market_ctx['fear_greed_advice'] = fear_greed.get('advice', '')
    market_ctx['fear_greed_emoji']  = fear_greed.get('emoji',  '😐')

    # ── Step 3: Technical analysis ────────────────────────────────────────────
    ohlcv         = raw['ohlcv']
    current_price = price_data['current_price']
    technical     = run_technical_analysis(ohlcv, current_price)

    # ── Step 4: Fundamental scoring ───────────────────────────────────────────
    fund_score = score_fundamentals(
        raw['fundamentals'], price_data, technical)

    # ── Step 5: Groq sentiment + recommendation ───────────────────────────────
    sentiment = run_sentiment_analysis(
        stock_name     = raw['display_name'],
        symbol         = raw['symbol'].replace('.NS', ''),
        news_data      = raw['news'],
        technical      = technical,
        fundamentals   = raw['fundamentals'],
        fund_score     = fund_score,
        price_data     = price_data,
        persona        = persona,
        market_context = market_ctx,
    )

    # ── Step 6: Final verdict ─────────────────────────────────────────────────
    final = _make_final_verdict(
        technical, fund_score, sentiment, current_price, persona)

    # ── Step 7: Build unified output ──────────────────────────────────────────
    return _build_output(
        raw        = raw,
        price_data = price_data,
        technical  = technical,
        fund_score = fund_score,
        sentiment  = sentiment,
        final      = final,
        market_ctx = market_ctx,
        fear_greed = fear_greed,
        persona    = persona,
    )


# ─────────────────────────────────────────────────────────────
# Final verdict logic
# ─────────────────────────────────────────────────────────────

def _make_final_verdict(
        technical:  dict,
        fund_score: dict,
        sentiment:  dict,
        current_price: float,
        persona:    str) -> dict:
    """
    Combines technical + AI signals into final BUY/HOLD/SELL.
    Decision logic mirrors your decision_engine.py combined signal.
    """
    tech_sig = technical.get('technical_signal', 'NEUTRAL')
    ai_sent  = sentiment.get('overall_sentiment', 'NEUTRAL')
    ai_rec   = sentiment.get('recommendation',    'HOLD')

    # Combined signal — identical to decision_engine.py
    if tech_sig == 'BULLISH' or ai_sent == 'BULLISH':
        combined = 'BULLISH'
    elif tech_sig == 'BEARISH' and ai_sent == 'BEARISH':
        combined = 'BEARISH'
    else:
        combined = 'NEUTRAL'

    # Final decision — AI recommendation takes priority,
    # combined signal acts as confirmation
    if ai_rec == 'BUY' and combined != 'BEARISH':
        verdict       = 'BUY'
        verdict_color = 'green'
    elif ai_rec == 'SELL' or (combined == 'BEARISH' and ai_rec != 'BUY'):
        verdict       = 'SELL'
        verdict_color = 'red'
    else:
        verdict       = 'HOLD'
        verdict_color = 'amber'

    # Target, SL, entry — AI values take priority, scorer as fallback
    target_price = sentiment.get('target_price') or fund_score.get('ai_target_price')
    stop_loss    = sentiment.get('stop_loss')
    entry_level  = (sentiment.get('entry_level') or
                    (fund_score.get('hold_entry_level') if verdict == 'HOLD' else None))
    entry_reason = (sentiment.get('entry_reason') or
                    (fund_score.get('hold_entry_reason') if verdict == 'HOLD' else None))

    # Sanity check: target must be > current price, SL must be < current price
    # Groq occasionally flips them — fix it silently
    if target_price and current_price:
        if target_price < current_price:
            # Groq returned a value below current — use scorer fallback
            target_price = fund_score.get('ai_target_price') or round(current_price * 1.10, 2)
    if stop_loss and current_price:
        if stop_loss > current_price:
            # Groq returned SL above current price — flip to reasonable SL
            stop_loss = round(current_price * 0.90, 2)

    # Upside % from current price to target
    upside_pct = None
    if target_price and current_price:
        upside_pct = round(
            ((target_price - current_price) / current_price) * 100, 1)

    # Risk-reward ratio
    rrr = None
    if target_price and stop_loss and current_price:
        gain = target_price - current_price
        loss = current_price - stop_loss
        if loss > 0:
            rrr = round(gain / loss, 1)

    cap_cat    = fund_score.get('cap_category', 'Mid Cap')
    thresholds = fund_score.get('cap_thresholds', {})

    return {
        'decision':          verdict,
        'verdict_color':     verdict_color,
        'combined_signal':   combined,
        'target_price':      target_price,
        'stop_loss':         stop_loss,
        'entry_level':       entry_level,
        'entry_reason':      entry_reason,
        'upside_pct':        upside_pct,
        'risk_reward':       rrr,
        'cap_category':      cap_cat,
        'stop_loss_pct':     thresholds.get('stop_loss',      -20),
        'profit_target_pct': thresholds.get('profit_target',   60),
        'confidence':        sentiment.get('confidence', 'MEDIUM'),
        'detail':            sentiment.get('recommendation_detail', ''),
        'risk_factors':      sentiment.get('risk_factors', ''),
    }


# ─────────────────────────────────────────────────────────────
# Output builder
# ─────────────────────────────────────────────────────────────

def _build_output(
        raw, price_data, technical, fund_score,
        sentiment, final, market_ctx, fear_greed, persona) -> dict:
    """
    Assembles the complete structured output that the API sends to frontend.
    """
    current_price = price_data['current_price']
    news_data     = raw['news']

    return {
        'status':       'success',
        'symbol':        raw['symbol'],
        'display_name':  raw['display_name'],
        'persona':       persona,

        # ── Price snapshot ────────────────────────────────────────────────────
        'price': {
            'current':      current_price,
            'label':        price_data.get('price_label'),
            'change':       price_data.get('change'),
            'change_pct':   price_data.get('change_pct'),
            'open':         price_data.get('open'),
            'high':         price_data.get('high'),
            'low':          price_data.get('low'),
            'prev_close':   price_data.get('prev_close'),
            'week_52_high': price_data.get('week_52_high'),
            'week_52_low':  price_data.get('week_52_low'),
            'volume':       price_data.get('volume'),
            'market_cap':   price_data.get('market_cap'),
            'sector':       price_data.get('sector'),
        },

        # ── Final verdict ─────────────────────────────────────────────────────
        'verdict': final,

        # ── Technical ─────────────────────────────────────────────────────────
        'technical': {
            'signal':           technical.get('technical_signal'),
            'bull_pct':         technical.get('bull_pct'),
            'bullish_score':    technical.get('bullish_score'),
            'bearish_score':    technical.get('bearish_score'),
            'table':            technical.get('trader_table', []),
            'notes':            technical.get('technical_notes', []),
            'support':          technical.get('support_levels', []),
            'resistance':       technical.get('resistance_levels', []),
            'insufficient':     technical.get('insufficient_indicators', []),
            'candles':          technical.get('candles_available', 0),
            'investor_summary': technical.get('investor_summary', ''),
            # Raw values for Groq prompt access
            'rsi':    technical.get('rsi'),
            'ema50':  technical.get('ema50'),
            'ema200': technical.get('ema200'),
        },

        # ── Fundamental ───────────────────────────────────────────────────────
        'fundamental': {
            'score':            fund_score.get('score'),
            'score_breakdown':  fund_score.get('score_breakdown', []),
            'table':            (fund_score.get('investor_table', [])
                                 if persona == 'investor'
                                 else fund_score.get('trader_table', [])),
            'pe_flag':          fund_score.get('pe_flag'),
            'valuation':        fund_score.get('valuation_verdict'),
            'target_basis':     fund_score.get('target_basis'),
            'investor_summary': fund_score.get('investor_summary', ''),
            'cap_category':     fund_score.get('cap_category'),
        },

        # ── News ──────────────────────────────────────────────────────────────
        'news': {
            'sentiment':          sentiment.get('news_sentiment'),
            'overall':            sentiment.get('overall_sentiment'),
            'company_headlines':  [n['title']
                                   for n in news_data.get('company_news', [])[:5]],
            'macro_headlines':    [n['title']
                                   for n in news_data.get('macro_news', [])[:3]],
            'total_articles':     news_data.get('total_fetched', 0),
        },

        # ── Market context ────────────────────────────────────────────────────
        'market': {
            'nifty50':           market_ctx.get('nifty50_price'),
            'nifty_change':      market_ctx.get('nifty50_change'),
            'sensex':            market_ctx.get('sensex_price'),
            'sensex_change':     market_ctx.get('sensex_change'),
            'mood':              market_ctx.get('market_mood'),
            'is_open':           market_ctx.get('market_status', {}).get('is_open', False),
            'fear_greed_score':  fear_greed.get('score'),
            'fear_greed_rating': fear_greed.get('rating'),
            'fear_greed_advice': fear_greed.get('advice'),
            'fear_greed_emoji':  fear_greed.get('emoji'),
        },

        # ── Meta ──────────────────────────────────────────────────────────────
        'meta': {
            'has_errors':    raw.get('has_errors', False),
            'error_summary': raw.get('error_summary'),
            'data_source':   'NSE API + Screener.in + Google News RSS + Groq',
        },
    }