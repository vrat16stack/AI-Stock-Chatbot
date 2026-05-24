"""
chatbot_technical.py
─────────────────────
Phase 2 — Technical Analysis Engine

IDENTICAL logic to your existing technical_analysis.py:
  - Same 7 indicators (RSI, MACD, BB, ADX, Stochastic, EMA50/200, OBV)
  - Same scoring weights (MACD crossover=2, ADX strong=2, RSI oversold=1.5 etc.)
  - Same MIN_CANDLES requirements
  - Same bull_pct thresholds (>=65 BULLISH, <=35 BEARISH)

Key difference from original:
  - Accepts pre-fetched OHLCV DataFrame instead of calling price_fetcher
    internally (Phase 1 already fetched it — no double fetch)
  - Returns two extra outputs:
      support_levels    → for HOLD entry suggestions
      resistance_levels → for target guidance
      trader_table      → structured rows for the expandable card
      investor_summary  → plain-English one-liner for investor mode
"""

import ta
import pandas as pd


# ── Identical to your technical_analysis.py ───────────────────────────────────
MIN_CANDLES = {
    'rsi':    15,
    'macd':   35,
    'bb':     21,
    'adx':    28,
    'stoch':  17,
    'ema50':  50,
    'ema200': 200,
    'obv':    10,
}


def _has_enough_data(df: pd.DataFrame, indicator_name: str) -> bool:
    required = MIN_CANDLES.get(indicator_name, 30)
    actual   = len(df)
    if actual < required:
        print(f"[technical] {indicator_name.upper()} skipped — "
              f"only {actual} candles, need {required}")
        return False
    return True


def run_technical_analysis(ohlcv_df: pd.DataFrame, current_price: float) -> dict:
    """
    Runs all 7 indicators on the OHLCV DataFrame from Phase 1.
    Scoring logic is identical to your calculate_indicators().

    Returns full result dict with raw values + signal + tables for UI.
    """
    df = ohlcv_df.copy() if not ohlcv_df.empty else pd.DataFrame()

    # Absolute minimum check — same as your original
    if df is None or len(df) < 15:
        return _empty_result(len(df) if df is not None else 0)

    close  = df['Close'].squeeze()
    high   = df['High'].squeeze()
    low    = df['Low'].squeeze()
    volume = df['Volume'].squeeze()

    bullish      = 0.0
    bearish      = 0.0
    notes        = []
    insufficient = []

    # ── 1. RSI — identical weights ────────────────────────────────────────────
    rsi = None
    if _has_enough_data(df, 'rsi'):
        try:
            rsi = round(float(
                ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]), 2)
            if rsi < 35:
                bullish += 1.5
                notes.append(f"RSI {rsi} → Oversold (Strong Bullish)")
            elif rsi < 50:
                bullish += 0.5
                notes.append(f"RSI {rsi} → Neutral-Bullish")
            elif rsi < 65:
                bearish += 0.5
                notes.append(f"RSI {rsi} → Neutral-Bearish")
            else:
                bearish += 1.5
                notes.append(f"RSI {rsi} → Overbought (Strong Bearish)")
        except Exception as e:
            print(f"[technical] RSI error: {e}")
            rsi = None
    else:
        insufficient.append('RSI')

    # ── 2. MACD — identical weights ───────────────────────────────────────────
    macd_val = macd_sig_val = None
    if _has_enough_data(df, 'macd'):
        try:
            macd_obj     = ta.trend.MACD(close, window_fast=12,
                                         window_slow=26, window_sign=9)
            macd_val     = round(float(macd_obj.macd().iloc[-1]),        4)
            macd_sig_val = round(float(macd_obj.macd_signal().iloc[-1]), 4)
            macd_hist    = round(float(macd_obj.macd_diff().iloc[-1]),   4)
            prev_hist    = round(float(macd_obj.macd_diff().iloc[-2]),   4)

            if macd_val > macd_sig_val and macd_hist > prev_hist:
                bullish += 2
                notes.append("MACD bullish crossover + increasing momentum")
            elif macd_val > macd_sig_val:
                bullish += 1
                notes.append(f"MACD {round(macd_val,2)} above signal → Bullish")
            elif macd_val < macd_sig_val and macd_hist < prev_hist:
                bearish += 2
                notes.append("MACD bearish crossover + decreasing momentum")
            else:
                bearish += 1
                notes.append(f"MACD {round(macd_val,2)} below signal → Bearish")
        except Exception as e:
            print(f"[technical] MACD error: {e}")
            macd_val = macd_sig_val = None
    else:
        insufficient.append('MACD')

    # ── 3. Bollinger Bands — identical weights ────────────────────────────────
    bb_upper = bb_mid = bb_lower = None
    if _has_enough_data(df, 'bb'):
        try:
            bb_obj   = ta.volatility.BollingerBands(close, window=20, window_dev=2)
            bb_upper = round(float(bb_obj.bollinger_hband().iloc[-1]), 2)
            bb_mid   = round(float(bb_obj.bollinger_mavg().iloc[-1]),  2)
            bb_lower = round(float(bb_obj.bollinger_lband().iloc[-1]), 2)
            bb_pct   = round(float(bb_obj.bollinger_pband().iloc[-1]), 4)

            if bb_pct < 0.2:
                bullish += 1.5
                notes.append(f"Price near lower BB (₹{bb_lower}) → Oversold bounce likely")
            elif bb_pct > 0.8:
                bearish += 1.5
                notes.append(f"Price near upper BB (₹{bb_upper}) → Overbought pullback likely")
            else:
                notes.append(f"Price within BB bands [₹{bb_lower}–₹{bb_upper}] — neutral zone")
        except Exception as e:
            print(f"[technical] Bollinger Bands error: {e}")
            bb_upper = bb_mid = bb_lower = None
    else:
        insufficient.append('Bollinger Bands')

    # ── 4. ADX — identical weights ────────────────────────────────────────────
    adx = adx_pos = adx_neg = None
    if _has_enough_data(df, 'adx'):
        try:
            adx_obj = ta.trend.ADXIndicator(high, low, close, window=14)
            adx     = round(float(adx_obj.adx().iloc[-1]),     2)
            adx_pos = round(float(adx_obj.adx_pos().iloc[-1]), 2)
            adx_neg = round(float(adx_obj.adx_neg().iloc[-1]), 2)

            if adx > 25:
                if adx_pos > adx_neg:
                    bullish += 2
                    notes.append(f"ADX {adx} → Strong uptrend confirmed "
                                 f"(+DI {adx_pos} > -DI {adx_neg})")
                else:
                    bearish += 2
                    notes.append(f"ADX {adx} → Strong downtrend confirmed "
                                 f"(-DI {adx_neg} > +DI {adx_pos})")
            else:
                notes.append(f"ADX {adx} → Weak trend (sideways market)")
        except Exception as e:
            print(f"[technical] ADX error: {e}")
            adx = None
    else:
        insufficient.append('ADX')

    # ── 5. Stochastic — identical weights ─────────────────────────────────────
    stoch_k = stoch_d = None
    if _has_enough_data(df, 'stoch'):
        try:
            stoch_obj = ta.momentum.StochasticOscillator(
                high, low, close, window=14, smooth_window=3)
            stoch_k = round(float(stoch_obj.stoch().iloc[-1]),        2)
            stoch_d = round(float(stoch_obj.stoch_signal().iloc[-1]), 2)

            if stoch_k < 20 and stoch_k > stoch_d:
                bullish += 1.5
                notes.append(f"Stochastic {stoch_k} → Oversold + bullish crossover")
            elif stoch_k < 20:
                bullish += 1
                notes.append(f"Stochastic {stoch_k} → Oversold zone")
            elif stoch_k > 80 and stoch_k < stoch_d:
                bearish += 1.5
                notes.append(f"Stochastic {stoch_k} → Overbought + bearish crossover")
            elif stoch_k > 80:
                bearish += 1
                notes.append(f"Stochastic {stoch_k} → Overbought zone")
            else:
                notes.append(f"Stochastic {stoch_k} → Neutral zone")
        except Exception as e:
            print(f"[technical] Stochastic error: {e}")
            stoch_k = stoch_d = None
    else:
        insufficient.append('Stochastic')

    # ── 6. EMA Cross — identical weights ──────────────────────────────────────
    ema50 = ema200 = None
    ema50_ok  = _has_enough_data(df, 'ema50')
    ema200_ok = _has_enough_data(df, 'ema200')

    if ema50_ok:
        try:
            ema50 = round(float(
                ta.trend.EMAIndicator(close, window=50)
                .ema_indicator().iloc[-1]), 2)
        except Exception as e:
            print(f"[technical] EMA50 error: {e}")

    if ema200_ok:
        try:
            ema200 = round(float(
                ta.trend.EMAIndicator(close, window=200)
                .ema_indicator().iloc[-1]), 2)
        except Exception as e:
            print(f"[technical] EMA200 error: {e}")

    # Identical EMA cross logic from your file
    if ema50 is not None and ema200 is not None:
        if ema50 > ema200 and current_price > ema50:
            bullish += 2
            notes.append(f"Golden Cross: EMA50 ({ema50}) > EMA200 ({ema200}) → Strong uptrend")
        elif ema50 > ema200:
            bullish += 1
            notes.append(f"EMA50 ({ema50}) above EMA200 ({ema200}) → Bullish trend")
        elif ema50 < ema200 and current_price < ema50:
            bearish += 2
            notes.append(f"Death Cross: EMA50 ({ema50}) < EMA200 ({ema200}) → Strong downtrend")
        else:
            bearish += 1
            notes.append(f"EMA50 ({ema50}) below EMA200 ({ema200}) → Bearish trend")
    elif ema50 is not None and ema200 is None:
        if current_price > ema50:
            bullish += 1
            notes.append(f"Price above EMA50 ({ema50}) → Short-term bullish "
                         f"(EMA200 insufficient data)")
        else:
            bearish += 1
            notes.append(f"Price below EMA50 ({ema50}) → Short-term bearish "
                         f"(EMA200 insufficient data)")
        insufficient.append('EMA200')
    else:
        insufficient.append('EMA50')
        insufficient.append('EMA200')

    # ── 7. OBV — identical weights ────────────────────────────────────────────
    obv_trend = None
    if _has_enough_data(df, 'obv'):
        try:
            obv        = ta.volume.OnBalanceVolumeIndicator(
                close, volume).on_balance_volume()
            obv_recent = obv.iloc[-1]
            obv_prev   = obv.iloc[-10]
            obv_trend  = "rising" if obv_recent > obv_prev else "falling"

            if obv_recent > obv_prev:
                bullish += 1
                notes.append("OBV rising → Smart money accumulating (Bullish)")
            else:
                bearish += 1
                notes.append("OBV falling → Smart money distributing (Bearish)")
        except Exception as e:
            print(f"[technical] OBV error: {e}")
    else:
        insufficient.append('OBV')

    # ── Final signal — identical thresholds from your code ────────────────────
    total    = bullish + bearish
    bull_pct = round((bullish / total * 100) if total > 0 else 50, 1)

    if bull_pct >= 65:
        signal = 'BULLISH'
    elif bull_pct <= 35:
        signal = 'BEARISH'
    else:
        signal = 'NEUTRAL'

    # Identical skipped-indicator note
    if insufficient:
        notes.append(f"Skipped (insufficient data): {', '.join(insufficient)}")

    # ── Support & resistance (extra — for HOLD entry level suggestions) ────────
    support, resistance = _compute_support_resistance(df, current_price, bb_lower, ema50)

    # ── Trader table rows (for expandable card in UI) ─────────────────────────
    trader_table = _build_trader_table(
        rsi, macd_val, macd_sig_val,
        bb_upper, bb_mid, bb_lower,
        adx, adx_pos, adx_neg,
        stoch_k, stoch_d,
        ema50, ema200,
        obv_trend, bull_pct, signal, insufficient
    )

    # ── Investor plain-English summary ────────────────────────────────────────
    investor_summary = _build_investor_summary(
        signal, bull_pct, rsi, ema50, ema200, current_price)

    return {
        # Raw values — same keys as your technical_analysis.py
        'rsi':           rsi,
        'macd':          macd_val,
        'macd_signal':   macd_sig_val,
        'bb_upper':      bb_upper,
        'bb_mid':        bb_mid,
        'bb_lower':      bb_lower,
        'adx':           adx,
        'adx_pos':       adx_pos,
        'adx_neg':       adx_neg,
        'stoch_k':       stoch_k,
        'stoch_d':       stoch_d,
        'ema50':         ema50,
        'ema200':        ema200,
        'obv_trend':     obv_trend,
        'current_price': round(current_price, 2),

        # Scoring — same keys as your file
        'bullish_score':           round(bullish, 1),
        'bearish_score':           round(bearish, 1),
        'bull_pct':                bull_pct,
        'signal_score':            bull_pct,
        'technical_signal':        signal,
        'technical_notes':         notes,
        'technical_summary':       ' | '.join(notes[:4]),
        'insufficient_indicators': insufficient,
        'candles_available':       len(df),

        # Extra for chatbot UI
        'support_levels':    support,
        'resistance_levels': resistance,
        'trader_table':      trader_table,
        'investor_summary':  investor_summary,
    }


# ─────────────────────────────────────────────────────────────
# Support & Resistance
# ─────────────────────────────────────────────────────────────

def _compute_support_resistance(
        df: pd.DataFrame,
        current_price: float,
        bb_lower: float | None,
        ema50: float | None) -> tuple[list, list]:
    """
    Computes key support and resistance price levels.
    Used for HOLD entry-level suggestions in the chatbot output.
    """
    try:
        close = df['Close'].squeeze()
        high  = df['High'].squeeze()
        low   = df['Low'].squeeze()

        recent_low  = low.tail(60)
        recent_high = high.tail(60)

        support    = []
        resistance = []

        # Support: significant lows below current price
        for l in sorted(recent_low.tolist()):
            if l < current_price * 0.99:
                rounded = round(l, 0)
                if not any(abs(rounded - s) < current_price * 0.015
                           for s in support):
                    support.append(rounded)
            if len(support) >= 3:
                break

        # Resistance: significant highs above current price
        for h in sorted(recent_high.tolist(), reverse=True):
            if h > current_price * 1.01:
                rounded = round(h, 0)
                if not any(abs(rounded - r) < current_price * 0.015
                           for r in resistance):
                    resistance.append(rounded)
            if len(resistance) >= 3:
                break

        # Add BB lower and EMA50 as support if below current price
        for level in [bb_lower, ema50]:
            if level and level < current_price * 0.99:
                rounded = round(level, 0)
                if not any(abs(rounded - s) < current_price * 0.015
                           for s in support):
                    support.append(rounded)

        support    = sorted(support, reverse=True)[:3]  # closest first
        resistance = sorted(resistance)[:3]

        return support, resistance
    except Exception:
        return [], []


# ─────────────────────────────────────────────────────────────
# Trader table builder
# ─────────────────────────────────────────────────────────────

def _build_trader_table(
        rsi, macd, macd_sig,
        bb_upper, bb_mid, bb_lower,
        adx, adx_pos, adx_neg,
        stoch_k, stoch_d,
        ema50, ema200,
        obv_trend, bull_pct, signal,
        insufficient) -> list[dict]:
    """
    Returns a list of row dicts for the full technical table in trader mode.
    Each row: { indicator, value, signal, interpretation }
    """
    rows = []

    def sig(bull_cond, bear_cond) -> str:
        if bull_cond: return "BULLISH"
        if bear_cond: return "BEARISH"
        return "NEUTRAL"

    # RSI
    if rsi is not None:
        rows.append({
            "indicator":      "RSI (14)",
            "value":          str(rsi),
            "signal":         sig(rsi < 50, rsi >= 65),
            "interpretation": (
                "Oversold — strong buy zone" if rsi < 35 else
                "Neutral-bullish"            if rsi < 50 else
                "Neutral-bearish"            if rsi < 65 else
                "Overbought — caution"),
        })
    elif 'RSI' in insufficient:
        rows.append({"indicator":"RSI (14)",
                     "value":"N/A","signal":"N/A",
                     "interpretation":"Insufficient data"})

    # MACD
    if macd is not None:
        rows.append({
            "indicator":      "MACD",
            "value":          f"{round(macd,3)} / Sig: {round(macd_sig,3)}",
            "signal":         sig(macd > macd_sig, macd < macd_sig),
            "interpretation": ("Bullish crossover" if macd > macd_sig
                               else "Bearish crossover"),
        })
    elif 'MACD' in insufficient:
        rows.append({"indicator":"MACD",
                     "value":"N/A","signal":"N/A",
                     "interpretation":"Insufficient data"})

    # Bollinger Bands
    if bb_upper is not None:
        rows.append({
            "indicator":      "Bollinger Bands",
            "value":          f"U:{bb_upper} M:{bb_mid} L:{bb_lower}",
            "signal":         "NEUTRAL",
            "interpretation": f"Range ₹{bb_lower} – ₹{bb_upper}",
        })
    elif 'Bollinger Bands' in insufficient:
        rows.append({"indicator":"Bollinger Bands",
                     "value":"N/A","signal":"N/A",
                     "interpretation":"Insufficient data"})

    # ADX
    if adx is not None:
        trend_dir = ("Uptrend" if adx_pos and adx_neg and adx_pos > adx_neg
                     else "Downtrend")
        rows.append({
            "indicator":      "ADX (Trend Strength)",
            "value":          str(adx),
            "signal":         sig(adx > 25 and adx_pos and adx_pos > adx_neg,
                                  adx > 25 and adx_neg and adx_neg > adx_pos),
            "interpretation": f"{'Strong' if adx > 25 else 'Weak'} trend — {trend_dir}",
        })
    elif 'ADX' in insufficient:
        rows.append({"indicator":"ADX",
                     "value":"N/A","signal":"N/A",
                     "interpretation":"Insufficient data"})

    # Stochastic
    if stoch_k is not None:
        rows.append({
            "indicator":      "Stochastic %K",
            "value":          f"{stoch_k} / %D: {stoch_d}",
            "signal":         sig(stoch_k < 20, stoch_k > 80),
            "interpretation": (
                "Oversold"    if stoch_k < 20 else
                "Overbought"  if stoch_k > 80 else
                "Neutral zone"),
        })
    elif 'Stochastic' in insufficient:
        rows.append({"indicator":"Stochastic",
                     "value":"N/A","signal":"N/A",
                     "interpretation":"Insufficient data"})

    # EMA Cross
    if ema50 is not None and ema200 is not None:
        cross = "Golden Cross ✓" if ema50 > ema200 else "Death Cross ✗"
        rows.append({
            "indicator":      "EMA 50 / 200",
            "value":          f"EMA50:{ema50} EMA200:{ema200}",
            "signal":         sig(ema50 > ema200, ema50 < ema200),
            "interpretation": cross,
        })
    elif ema50 is not None:
        rows.append({
            "indicator":      "EMA 50",
            "value":          str(ema50),
            "signal":         "NEUTRAL",
            "interpretation": "EMA200 N/A — need 200+ candles",
        })
    else:
        rows.append({"indicator":"EMA 50/200",
                     "value":"N/A","signal":"N/A",
                     "interpretation":"Insufficient data"})

    # OBV
    if obv_trend is not None:
        rows.append({
            "indicator":      "OBV (Volume Flow)",
            "value":          obv_trend.upper(),
            "signal":         sig(obv_trend == "rising", obv_trend == "falling"),
            "interpretation": ("Smart money accumulating"
                               if obv_trend == "rising"
                               else "Smart money distributing"),
        })
    elif 'OBV' in insufficient:
        rows.append({"indicator":"OBV",
                     "value":"N/A","signal":"N/A",
                     "interpretation":"Insufficient data"})

    # Overall score row
    rows.append({
        "indicator":      "OVERALL BULL SCORE",
        "value":          f"{bull_pct}%",
        "signal":         signal,
        "interpretation": f"{signal} — {bull_pct}% of weighted indicators bullish",
    })

    return rows


# ─────────────────────────────────────────────────────────────
# Investor plain-English summary
# ─────────────────────────────────────────────────────────────

def _build_investor_summary(
        signal: str, bull_pct: float,
        rsi: float | None,
        ema50: float | None, ema200: float | None,
        current_price: float) -> str:

    parts = []

    if signal == 'BULLISH':
        parts.append(f"The stock's chart is looking positive — "
                     f"{round(bull_pct)}% of technical signals are in its favour.")
    elif signal == 'BEARISH':
        parts.append(f"The stock's chart is under pressure — "
                     f"only {round(bull_pct)}% of signals are positive.")
    else:
        parts.append(f"The stock's chart is giving mixed signals — "
                     f"{round(bull_pct)}% positive, {round(100-bull_pct)}% cautious.")

    if rsi is not None:
        if rsi < 35:
            parts.append(
                f"The stock appears oversold (RSI {rsi}) — it may have fallen "
                f"more than warranted, which can be a buying opportunity.")
        elif rsi > 65:
            parts.append(
                f"The stock looks stretched (RSI {rsi}) — it has risen fast "
                f"recently and may slow down or pull back slightly.")

    if ema50 is not None and ema200 is not None:
        if ema50 > ema200:
            parts.append(
                "The short-term trend is stronger than the long-term average "
                "— a positive sign for momentum.")
        else:
            parts.append(
                "The short-term trend is weaker than the long-term average "
                "— the stock is still in recovery mode.")

    return " ".join(parts)


# ─────────────────────────────────────────────────────────────
# Empty result (< 15 candles)
# ─────────────────────────────────────────────────────────────

def _empty_result(candles: int) -> dict:
    return {
        'rsi':None,'macd':None,'macd_signal':None,
        'bb_upper':None,'bb_mid':None,'bb_lower':None,
        'adx':None,'adx_pos':None,'adx_neg':None,
        'stoch_k':None,'stoch_d':None,
        'ema50':None,'ema200':None,'obv_trend':None,
        'current_price':0,
        'bullish_score':0,'bearish_score':0,
        'bull_pct':50,'signal_score':50,
        'technical_signal':'NEUTRAL',
        'technical_notes':['Insufficient data for technical analysis'],
        'technical_summary':'Insufficient data',
        'insufficient_indicators':['RSI','MACD','Bollinger Bands',
                                   'ADX','Stochastic','EMA50','EMA200','OBV'],
        'candles_available':candles,
        'support_levels':[],'resistance_levels':[],
        'trader_table':[],
        'investor_summary':'Not enough price history for technical analysis.',
    }
