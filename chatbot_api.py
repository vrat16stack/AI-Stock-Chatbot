"""
chatbot_api.py
───────────────
Phase 3 — FastAPI Backend

Endpoints:
  POST /chat    → main chat handler (analysis + general Q&A)
  GET  /health  → health check for Render

Routing logic:
  1. Detect language (English / Hinglish)
  2. Extract stock symbol from message or conversation history
  3. If stock + analysis intent → run full Phase 2 pipeline
  4. Else → Groq general Q&A (always ties back to a stock example)

Session memory: frontend sends last N messages with every request.
Hinglish: detected via keyword heuristic + langdetect fallback.
"""

import os
import re
import time
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

from chatbot_analysis_engine import analyse_stock
from chatbot_price_fetcher   import resolve_ticker, is_market_open

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = os.getenv("GROQ_MODEL",   "llama3-70b-8192")

app = FastAPI(title="Stock AI Chatbot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ai-stock-chatbot-v2.vercel.app/"],       # tighten to Vercel URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role:    str       # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    persona: str                    = "trader"
    history: List[ChatMessage]      = []

class ChatResponse(BaseModel):
    type:           str             # "analysis" | "general" | "error"
    message:        str             # summary text shown in chat bubble
    analysis:       Optional[dict]  = None   # full payload for expandable card
    detected_stock: Optional[str]  = None
    language:       str             = "en"


# ─────────────────────────────────────────────────────────────
# Language detection
# ─────────────────────────────────────────────────────────────

_HINGLISH_WORDS = {
    "kya","hai","hoga","karo","batao","kaisa","kaise","mujhe","chahiye",
    "accha","theek","sahi","galat","abhi","matlab","seedha","bata","kar",
    "nahi","nhi","yaar","bhai","bol","lagta","lagti","dekho","dekh",
    "kitna","kitni","kyun","kyunki","toh","phir","aur","lekin","par",
    "woh","yeh","iska","uska","inko","kab","kahan","kaun","kuch","sab",
    "sirf","bas","kharidna","bechna","paisa","batana","karunga","lena",
    "dena","achha","thoda","bahut","zyada","kam","loss","profit","invest",
}

def detect_language(text: str) -> str:
    lower = text.lower()
    words = re.findall(r'\b\w+\b', lower)
    hits  = sum(1 for w in words if w in _HINGLISH_WORDS)
    if hits >= 2:
        return "hi"
    try:
        from langdetect import detect
        lang = detect(text)
        return "hi" if lang in ("hi", "ur", "mr") else "en"
    except Exception:
        return "en"


# ─────────────────────────────────────────────────────────────
# Stock symbol extraction
# ─────────────────────────────────────────────────────────────

# Words that suggest the user wants stock analysis
_ANALYSIS_TRIGGERS = [
    r'\b(analyse|analyze|analysis|check|buy|sell|hold|invest|lagana|kharidna|bechna)\b',
    r'\b(should i|kya main|kya mujhe|lena chahiye|entry|target|stop.?loss)\b',
    r'\b(kaise hai|kaisa hai|kaisi hai|kya sochte|kya lagta|batao|bata)\b',
    r'\b(recommendation|suggest|advice|worth|achha hai|sahi hai|theek hai)\b',
    r'\b(upside|downside|potential|future|outlook|view)\b',
]

# Words that mean "this stock / same stock / its competitor"
_CONTEXT_REFS = [
    "iska","uska","iski","uski","iske","usi","isi",
    "this stock","same stock","that stock","this one","this company",
    "its competitor","competitor","rival","yeh wala","woh wala",
    "dusra","doosra","aur ek","another one",
]

# Stop-words — common caps words that are NOT stock tickers
_NOT_TICKERS = {
    "RSI","MACD","EMA","OBV","ADX","NSE","BSE","IPO","FII","DII",
    "RBI","SEBI","GDP","CPI","CEO","CFO","MD","AI","API","BUY",
    "SELL","HOLD","YES","NO","OK","P","E","B","D","N","A","I",
    "THE","FOR","AND","OR","IN","AT","ON","IS","IT","BE","TO",
    "OF","AS","BY","US","UP","IF","SO","DO","GO","MY","WE",
}


def _find_stock_in_text(text: str) -> Optional[str]:
    """Scans text for a recognisable NSE stock name or ticker."""
    from chatbot_price_fetcher import _ALIASES

    text_upper = text.upper()
    text_lower = text.lower()

    # Check alias table — longest match first to avoid partial matches
    for alias in sorted(_ALIASES.keys(), key=len, reverse=True):
        # Word-boundary-like check
        pattern = r'\b' + re.escape(alias) + r'\b'
        if re.search(pattern, text_upper):
            return alias

    # All-caps words 2–12 chars that aren't stop-words (likely raw tickers)
    caps = re.findall(r'\b[A-Z]{2,12}\b', text)
    for c in caps:
        if c not in _NOT_TICKERS:
            return c

    return None


def extract_stock_symbol(
        message: str,
        history: List[ChatMessage]) -> Optional[str]:
    """
    Extracts stock symbol from current message.
    If message is a context reference (iska/this stock/etc.),
    walks back through history to find the last mentioned stock.
    """
    msg_lower = message.lower()

    # Context reference — look in history
    if any(ref in msg_lower for ref in _CONTEXT_REFS):
        for msg in reversed(history):
            sym = _find_stock_in_text(msg.content)
            if sym:
                return sym
        return None

    return _find_stock_in_text(message)


def is_analysis_request(message: str) -> bool:
    """Returns True if message is asking for stock analysis."""
    lower = message.lower()
    for pattern in _ANALYSIS_TRIGGERS:
        if re.search(pattern, lower, re.IGNORECASE):
            return True
    return False


# ─────────────────────────────────────────────────────────────
# Analysis summary formatter
# ─────────────────────────────────────────────────────────────

def format_analysis_bubble(
        result: dict,
        language: str,
        persona: str) -> str:
    """
    Formats the short chat-bubble summary from the full analysis result.
    Trader: numbers-forward. Investor: plain English. Both: Hinglish if detected.
    """
    v         = result.get('verdict') or {}
    p         = result.get('price')   or {}
    name      = result.get('display_name', 'Unknown')
    sym       = (result.get('symbol') or '').replace('.NS', '')
    decision  = v.get('decision', 'HOLD')
    emoji     = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴"}.get(decision, "⚪")

    def fmt_price(x):
        if x is None: return "N/A"
        return f"₹{x:,.2f}"

    # ── Hinglish bubble ───────────────────────────────────────────────────────
    if language == "hi":
        if decision == "BUY":
            intro = f"{emoji} **{name} ({sym})** — AI bol raha hai **BUY karo**."
        elif decision == "HOLD":
            intro = (f"{emoji} **{name} ({sym})** — AI bol raha hai **HOLD karo**, "
                     f"abhi direct entry mat lo.")
        else:
            intro = (f"{emoji} **{name} ({sym})** — AI ka suggestion hai "
                     f"**SELL / avoid karo**.")

        lines = [intro, ""]
        lines.append(f"💰 **Current Price:** {fmt_price(p['current'])}  "
                     f"({p.get('label','')})")
        if v.get('target_price'):
            lines.append(f"🎯 **Target:** {fmt_price(v['target_price'])}  "
                         f"(+{v.get('upside_pct','?')}% upside)")
        if v.get('stop_loss'):
            lines.append(f"🛑 **Stop Loss:** {fmt_price(v['stop_loss'])}")
        if decision == "HOLD" and v.get('entry_level'):
            lines.append(f"📍 **Entry Level:** {fmt_price(v['entry_level'])}")
            if v.get('entry_reason'):
                lines.append(f"   _{v['entry_reason']}_")
        lines.append("")
        lines.append(f"📊 **Technical:** {result['technical']['signal']} "
                     f"({result['technical']['bull_pct']}% bullish)")
        lines.append(f"📰 **News:** {result['news']['sentiment']}")
        lines.append(f"💡 **Confidence:** {v['confidence']}")
        lines.append("")
        lines.append(f"_{v.get('detail','')}_")
        lines.append("")
        lines.append("👇 **Full analysis neeche dekho** — "
                     "technical table, fundamentals, aur news.")

    # ── Investor English bubble ───────────────────────────────────────────────
    elif persona == "investor":
        if decision == "BUY":
            intro = f"{emoji} **{name} ({sym})** — The AI recommends **BUY**."
        elif decision == "HOLD":
            intro = (f"{emoji} **{name} ({sym})** — The AI says **HOLD** — "
                     f"wait for a better entry price.")
        else:
            intro = (f"{emoji} **{name} ({sym})** — "
                     f"The AI suggests **AVOID / SELL**.")

        lines = [intro, ""]
        lines.append(f"💰 **Price:** {fmt_price(p['current'])}  "
                     f"_{p.get('label','')}_")
        if v.get('target_price'):
            lines.append(f"🎯 **Target price:** {fmt_price(v['target_price'])}  "
                         f"(potential {v.get('upside_pct','?')}% gain)")
        if v.get('stop_loss'):
            lines.append(f"🛑 **Exit if it falls to:** {fmt_price(v['stop_loss'])}")
        if decision == "HOLD" and v.get('entry_level'):
            lines.append(f"📍 **Better entry price:** {fmt_price(v['entry_level'])}")
            if v.get('entry_reason'):
                lines.append(f"   _{v['entry_reason']}_")
        lines.append("")
        lines.append(f"📊 Chart signal: **{result['technical']['signal']}**")
        lines.append(f"🏢 Fundamentals score: **{result['fundamental']['score']}/100**")
        lines.append(f"📰 Recent news: **{result['news']['sentiment']}**")
        lines.append(f"😨 Market mood: **{result['market'].get('fear_greed_rating','N/A')}** "
                     f"{result['market'].get('fear_greed_emoji','')}")
        lines.append("")
        lines.append(f"_{v.get('detail','')}_")
        lines.append("")
        lines.append("👇 Tap **View Full Analysis** below for all details.")

    # ── Trader English bubble ─────────────────────────────────────────────────
    else:
        chg_str = (f"{p.get('change_pct',0):+.2f}%"
                   if p.get('change_pct') is not None else "")
        intro = (f"{emoji} **{name} ({sym})** — "
                 f"`{decision}` | Confidence: {v['confidence']}")

        lines = [intro, ""]
        lines.append(f"**Price:** {fmt_price(p['current'])} ({chg_str})  "
                     f"_{p.get('label','')}_")
        lines.append(f"**52W:** {fmt_price(p.get('week_52_low'))} – "
                     f"{fmt_price(p.get('week_52_high'))}")
        lines.append(f"**Cap:** {v.get('cap_category','N/A')}")
        lines.append("")
        if v.get('target_price'):
            lines.append(f"🎯 **Target:** {fmt_price(v['target_price'])}  "
                         f"(+{v.get('upside_pct','?')}%)")
        if v.get('stop_loss'):
            lines.append(f"🛑 **Stop Loss:** {fmt_price(v['stop_loss'])}")
        if v.get('risk_reward'):
            lines.append(f"⚖️ **R:R:** 1 : {v['risk_reward']}")
        if decision == "HOLD" and v.get('entry_level'):
            lines.append(f"📍 **Entry Level:** {fmt_price(v['entry_level'])}")
            if v.get('entry_reason'):
                lines.append(f"   _{v['entry_reason']}_")
        lines.append("")
        lines.append(
            f"**Tech:** {result['technical']['signal']} "
            f"({result['technical']['bull_pct']}% bull)  |  "
            f"**News:** {result['news']['sentiment']}  |  "
            f"**F&G:** {result['market'].get('fear_greed_score','N/A')} "
            f"({result['market'].get('fear_greed_rating','N/A')})")
        lines.append("")
        lines.append(f"_{v.get('detail','')}_")
        if v.get('risk_factors'):
            lines.append(f"\n⚠️ **Risks:** {v['risk_factors']}")
        lines.append("")
        lines.append("👇 Expand **Full Analysis** card below.")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# General Q&A via Groq
# ─────────────────────────────────────────────────────────────

def answer_general_question(
        message:  str,
        history:  List[ChatMessage],
        persona:  str,
        language: str) -> str:
    """
    Answers any stock market question using Groq.
    Always tries to tie the answer to a real NSE stock example.
    Replies in the same language the user used.
    """
    if not GROQ_API_KEY:
        return ("GROQ_API_KEY not set. Please add it to backend/.env "
                "and restart the server.")

    client = Groq(api_key=GROQ_API_KEY)

    lang_instr = (
        "The user is writing in Hinglish (Hindi + English mixed). "
        "Reply in the same casual Hinglish style — mix Hindi and English naturally. "
        "Do NOT reply in pure Hindi or overly formal English."
        if language == "hi"
        else "Reply in clear, professional English."
    )

    persona_instr = (
        "The user is a TRADER who understands technical analysis, RSI, MACD, "
        "chart patterns, and short-term price action. Use technical language freely."
        if persona == "trader"
        else
        "The user is an INVESTOR who understands stocks but doesn't track them daily. "
        "Use simple language. Explain any technical term briefly in brackets."
    )

    # Last 8 messages for context
    history_msgs = [
        {"role": m.role, "content": m.content}
        for m in history[-8:]
    ]

    system = f"""You are an expert Indian stock market analyst and advisor for NSE/BSE stocks.

{lang_instr}
{persona_instr}

RULES:
1. Only answer questions related to Indian stock market, NSE/BSE stocks, trading,
   investing, economy, or personal finance. If completely unrelated, politely redirect.
2. ALWAYS try to tie your answer to a specific NSE stock example to make it practical.
   Example: explaining RSI → show what RSI looks like for RELIANCE or HDFCBANK right now.
   Example: explaining sector rotation → name actual NSE sectors and example stocks.
3. Keep answers concise but complete.
4. Never give specific BUY/SELL advice in general Q&A — say "ask me to analyse
   [stock name] for a specific recommendation."
5. If the user referenced a specific stock earlier in the conversation, use that context.
6. End responses with a natural follow-up like:
   "Want me to run a full analysis on [stock]?" when relevant.
7. Do not use excessive markdown — keep it readable in a chat bubble."""

    try:
        resp = client.chat.completions.create(
            model    = GROQ_MODEL,
            messages = [
                {"role": "system", "content": system},
                *history_msgs,
                {"role": "user",   "content": message},
            ],
            max_tokens  = 500,
            temperature = 0.4,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Sorry, I couldn't process that right now. Error: {e}"


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    message = req.message.strip()
    persona = req.persona.lower()
    history = req.history

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    # ── Detect language ───────────────────────────────────────────────────────
    language = detect_language(message)

    # ── Extract stock symbol ──────────────────────────────────────────────────
    detected_stock = extract_stock_symbol(message, history)

    # ── Decide route ─────────────────────────────────────────────────────────
    # Analysis if: stock found AND (analysis intent OR stock name alone)
    wants_analysis = (
        detected_stock is not None and
        (is_analysis_request(message) or
         detected_stock.upper() in message.upper())
    )

    # ── Route: Stock Analysis ─────────────────────────────────────────────────
    if wants_analysis:
        try:
            result = analyse_stock(detected_stock, persona)

            if result.get('status') == 'error':
                err = result.get('error', 'Unknown error')
                if language == "hi":
                    reply = (f"Yaar, **{detected_stock}** ka data nahi mila. "
                             f"{err}\n\nSahi NSE ticker daalo aur dobara try karo.")
                else:
                    reply = (f"Couldn't find data for **{detected_stock}**. {err}\n\n"
                             f"Try using the exact NSE symbol "
                             f"(e.g. TATAMOTORS, HDFCBANK, RELIANCE).")
                return ChatResponse(
                    type="error", message=reply,
                    language=language, detected_stock=detected_stock)

            summary = format_analysis_bubble(result, language, persona)

            return ChatResponse(
                type           = "analysis",
                message        = summary,
                analysis       = result,
                detected_stock = detected_stock,
                language       = language,
            )

        except Exception as e:
            msg = (
                f"Analysis mein kuch gadbad ho gayi **{detected_stock}** ke liye: {e}"
                if language == "hi"
                else f"Something went wrong analysing **{detected_stock}**: {e}"
            )
            return ChatResponse(
                type="error", message=msg,
                language=language, detected_stock=detected_stock)

    # ── Route: General Q&A ────────────────────────────────────────────────────
    answer = answer_general_question(message, history, persona, language)
    return ChatResponse(
        type           = "general",
        message        = answer,
        detected_stock = detected_stock,
        language       = language,
    )


@app.get("/health")
def health():
    mkt = is_market_open()
    return {
        "status":        "ok",
        "market_open":   mkt["is_open"],
        "market_reason": mkt["reason"],
        "market_as_of":  str(mkt["as_of_date"]),
        "groq_key_set":  bool(GROQ_API_KEY),
    }


@app.get("/")
def root():
    return {"message": "Stock AI Chatbot API is running. POST /chat to use."}
