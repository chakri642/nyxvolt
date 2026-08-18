import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
import anthropic

log = logging.getLogger(__name__)

HISTORY_PATH = Path(__file__).parent / "history.json"
_client = None

SYSTEM_PROMPT = """You pick topics for a faceless data-viz Instagram Reel channel. Every reel shows a line chart of an asset over time with dramatic event labels popping in, plus a bold voiceover.

You MUST return valid JSON with this exact shape:
{
  "ticker": "yfinance-compatible symbol (e.g. BTC-USD, AAPL, TSLA, ETH-USD, ^GSPC, NVDA, GME)",
  "start_date": "YYYY-MM-DD (must have real price data on/after this date)",
  "end_date": "YYYY-MM-DD or null for today",
  "initial_investment": 100,
  "hook": "Punchy 6-10 word opening line. Personal, second-person, curiosity or shock (e.g. 'If you invested $100 in Bitcoin the day you were born').",
  "script": "25-30 second voiceover script. Opens with hook, walks through 2-3 dramatic moments, ends with the final dollar reveal. Conversational, hyped, no filler. Around 60-75 words.",
  "final_line": "One-line dollar reveal shown big at end (e.g. 'Worth $47,000 today').",
  "events": [
    {"date": "YYYY-MM-DD", "label": "Short dramatic label under 30 chars (e.g. 'COVID crash -34%')"}
  ],
  "caption": "2-line Instagram caption. Line 1: punchy statement/opinion tied to this specific asset. Line 2: an easy-to-answer question that begs a comment (e.g. 'Would you have held? or sold at the top?'). Tasteful emojis OK (max 2). NO hashtags in the caption. NO em/en dashes — use commas or periods only (dashes look AI-generated and hurt reach).",
  "hashtags": ["4-6 niche-specific tags without # prefix, lowercase, no spaces. e.g. for BTC-USD: ['bitcoin','btc','crypto','investing','hodl']. Do NOT include generic spam like 'viral' 'fyp' 'trending' — those are downweighted."],
  "niche": "one of: crypto, stocks, indexes"
}

Rules:
- Pick topics with REAL drama: crashes, bubbles, meme-stock squeezes, all-time highs, bankruptcies, viral moments.
- 3-5 event labels, spread across the timeline.
- Ticker MUST exist on yfinance. Safe examples: BTC-USD, ETH-USD, DOGE-USD, AAPL, TSLA, NVDA, GME, AMC, GOOGL, MSFT, AMZN, META, NFLX, ^GSPC (S&P 500), ^IXIC (Nasdaq).
- Start date must be one where the ticker actually traded (BTC-USD from 2014-09, ETH from 2017, TSLA from 2010-06, GME meme era ~2020, etc).
- NEVER repeat any topic from the DO-NOT-REPEAT list below.
- Output ONLY the JSON. No markdown, no code fences, no commentary."""


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text())
    except json.JSONDecodeError:
        log.warning("history.json corrupt, starting fresh")
        return []


def _save_to_history(entry: dict) -> None:
    hist = _load_history()
    hist.append(entry)
    HISTORY_PATH.write_text(json.dumps(hist, indent=2))


def _format_dont_repeat(hist: list) -> str:
    if not hist:
        return "(no prior topics — you have a blank slate)"
    lines = []
    for e in hist[-50:]:  # cap at last 50 to keep prompt lean
        lines.append(f"- {e['ticker']} {e['start_date']}→{e.get('end_date') or 'today'} | hook: \"{e['hook']}\"")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Strip code fences if Claude added them, then parse."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def pick_topic() -> dict:
    """Ask Claude for a fresh topic, avoiding anything in history.json.
    Returns the full topic dict and appends it to history on success."""
    hist = _load_history()
    dont_repeat = _format_dont_repeat(hist)

    log.info(f"Picking topic (history has {len(hist)} prior entries)")
    client = _get_client()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"DO-NOT-REPEAT list (past reels — pick something clearly different):\n{dont_repeat}\n\n"
                "Pick one fresh topic now. Return the JSON."
            ),
        }],
    )
    raw = msg.content[0].text
    topic = _extract_json(raw)

    entry = {
        "picked_at": datetime.utcnow().isoformat() + "Z",
        "ticker": topic["ticker"],
        "start_date": topic["start_date"],
        "end_date": topic.get("end_date"),
        "hook": topic["hook"],
        "niche": topic.get("niche", "unknown"),
    }
    _save_to_history(entry)
    log.info(f"Picked: {topic['ticker']} | \"{topic['hook']}\"")
    return topic
