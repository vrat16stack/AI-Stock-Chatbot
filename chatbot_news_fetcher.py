"""
chatbot_news_fetcher.py
────────────────────────
Phase 1 — News Data Layer

Fetches stock-specific + macro India news using Google News RSS.
100% free — no API key required.

Mirrors the same tiered news logic from your news_sentiment.py:
  Tier 1 → full article text  (high confidence)
  Tier 2 → RSS snippet        (medium confidence)
  Tier 3 → headline only      (low confidence)

Returns structured news list ready for the Groq prompt.
"""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import re
from datetime import datetime, timedelta, timezone
from chatbot_price_fetcher import resolve_ticker


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _rss_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"


def _clean_title(title: str) -> str:
    """Remove ' — Source Name' suffix Google News appends."""
    if not title:
        return ""
    if " - " in title:
        parts = title.rsplit(" - ", 1)
        if len(parts[1]) < 45:
            return parts[0].strip()
    return title.strip()


def _parse_pub_date(entry_text: str | None) -> datetime:
    """Parse RSS pubDate string to UTC datetime."""
    if not entry_text:
        return datetime.now(timezone.utc)
    try:
        # Common RSS date format: "Mon, 19 May 2025 10:30:00 GMT"
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(entry_text).astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _age_days(pub_dt: datetime) -> int:
    return (datetime.now(timezone.utc) - pub_dt).days


def _fetch_full_article(url: str) -> str | None:
    """
    Tier 1: Try to fetch full article text.
    Same approach as your existing news_sentiment.py _fetch_full_article().
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=8)
        if resp.status_code == 200:
            text  = re.sub(r"<[^>]+>", " ", resp.text)
            text  = re.sub(r"\s+", " ", text).strip()
            words = text.split()
            return " ".join(words[:700]) if len(words) > 50 else None
    except Exception:
        pass
    return None


def _fetch_rss(query: str, max_items: int = 8) -> list[dict]:
    """
    Fetches items from Google News RSS for a query.
    Returns list of raw article dicts with tiered content.
    """
    articles = []
    try:
        req = urllib.request.Request(_rss_url(query), headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()

        root  = ET.fromstring(content)
        items = root.findall(".//item")

        for item in items[:max_items]:
            title_el   = item.find("title")
            pubdate_el = item.find("pubDate")
            desc_el    = item.find("description")
            link_el    = item.find("link")

            if title_el is None:
                continue

            title   = _clean_title(title_el.text or "")
            pub_dt  = _parse_pub_date(pubdate_el.text if pubdate_el is not None else None)
            age     = _age_days(pub_dt)

            # Skip articles older than 14 days
            if age > 14:
                continue

            article = {
                "title":      title,
                "published":  pub_dt.strftime("%d %b %Y"),
                "age_days":   age,
                "source":     _extract_source(title_el.text or ""),
                "content":    None,
                "tier":       3,
                "confidence": "low",
                "url":        link_el.text if link_el is not None else "",
            }

            # Tier 2: RSS description snippet
            if desc_el is not None and desc_el.text:
                clean = re.sub(r"<[^>]+>", " ", desc_el.text).strip()
                if len(clean) > 80:
                    article["content"]    = clean[:600]
                    article["tier"]       = 2
                    article["confidence"] = "medium"

            # Tier 1: Full article
            if article["url"]:
                full = _fetch_full_article(article["url"])
                if full:
                    article["content"]    = full
                    article["tier"]       = 1
                    article["confidence"] = "high"

            articles.append(article)

    except Exception as e:
        pass

    return articles


def _extract_source(raw_title: str) -> str:
    """Extract source name from 'Headline - Source Name'."""
    if " - " in raw_title:
        return raw_title.rsplit(" - ", 1)[-1].strip()
    return "Unknown"


# ─────────────────────────────────────────────────────────────
# Main fetch function
# ─────────────────────────────────────────────────────────────

def fetch_news(symbol: str, company_name: str | None = None, max_articles: int = 8) -> dict:
    """
    Fetches company-specific + macro India news.

    Returns:
    {
        'company_news': [ { title, published, age_days, source, content, tier, confidence, url }, ... ],
        'macro_news':   [ { ... }, ... ],
        'total_fetched': int,
        'error':         None | str,
    }
    """
    nse_sym, yf_sym = resolve_ticker(symbol)
    ticker      = yf_sym
    sym_clean   = nse_sym
    search_name = company_name or sym_clean

    # ── Company news ──────────────────────────────────────────────────────────
    company_articles = []
    seen_titles      = set()

    for query in [
        f"{search_name} NSE stock India",
        f"{sym_clean} share price NSE",
        f"{search_name} earnings results India",
    ]:
        for art in _fetch_rss(query, max_items=6):
            key = art["title"].lower().strip()
            if key and key not in seen_titles:
                seen_titles.add(key)
                company_articles.append(art)
        if len(company_articles) >= max_articles:
            break

    # Sort by recency, cap at max_articles
    company_articles = sorted(company_articles, key=lambda x: x["age_days"])[:max_articles]

    # ── Macro / India market news ─────────────────────────────────────────────
    macro_articles = []
    macro_seen     = set()

    for query in [
        "NSE Nifty 50 India stock market today",
        "RBI repo rate India economy 2025",
        "Sensex India market outlook",
    ]:
        for art in _fetch_rss(query, max_items=3):
            key = art["title"].lower().strip()
            if key and key not in macro_seen:
                macro_seen.add(key)
                macro_articles.append(art)

    macro_articles = sorted(macro_articles, key=lambda x: x["age_days"])[:5]

    total = len(company_articles) + len(macro_articles)

    return {
        "company_news":  company_articles,
        "macro_news":    macro_articles,
        "total_fetched": total,
        "error": None if total > 0
                 else "No recent news found. Analysis will proceed without news context.",
    }


def format_news_for_prompt(news_data: dict) -> str:
    """
    Formats news into the same text block format used in your
    existing news_sentiment.py analyze_sentiment_with_groq().
    """
    tier_labels = {
        1: "[Full Article]",
        2: "[Snippet]",
        3: "[Headline Only — low confidence]",
    }
    lines = []

    if news_data["company_news"]:
        lines.append("=== COMPANY NEWS (last 14 days) ===")
        for i, a in enumerate(news_data["company_news"], 1):
            label = tier_labels.get(a.get("tier", 3), "[Headline]")
            body  = a.get("content") or a["title"]
            lines.append(
                f"{i}. {label} {a['title']} ({a['published']}) | {a['source']}\n"
                f"   {body[:300]}"
            )

    if news_data["macro_news"]:
        lines.append("\n=== INDIA MACRO / MARKET NEWS ===")
        for i, a in enumerate(news_data["macro_news"], 1):
            lines.append(f"{i}. {a['title']} ({a['published']}) | {a['source']}")

    return "\n".join(lines) if lines else "No recent news available."