import logging
import re
import time
from pathlib import Path

from config import CLIPS_OUTPUT
from data_viz.data import fetch, portfolio_value
from data_viz.render import render
from data_viz.topic import pick_topic
from data_viz.voice import synthesize

log = logging.getLogger(__name__)


BRAND_FOOTER = "Data viz daily by @nyxvolt"


def run(voice: bool = True, post: bool = False) -> Path:
    """End-to-end: pick fresh topic → fetch data → optional voiceover → render → save → optional post."""
    ts = int(time.time())
    log.info("=== Data-viz pipeline start ===")

    topic = pick_topic()
    log.info(f"Topic: {topic['ticker']} | \"{topic['hook']}\"")

    prices = fetch(topic["ticker"], topic["start_date"], topic.get("end_date"))
    initial = float(topic.get("initial_investment", 100))
    pv = portfolio_value(prices, initial)
    final_value = float(pv.iloc[-1])
    log.info(f"Final portfolio: ${final_value:,.0f} (from ${initial:,.0f})")

    # Prefer Claude's final_line but sanity-check the number matches what data says.
    # If Claude's number is wildly off, fall back to computed value.
    final_line = _reconcile_final_line(topic.get("final_line", ""), final_value)

    audio_path = None
    if voice and topic.get("script"):
        audio_path = CLIPS_OUTPUT.parent / "voice" / f"viz_{ts}.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        synthesize(topic["script"], audio_path)

    safe_ticker = re.sub(r"[^a-zA-Z0-9_-]+", "_", topic["ticker"])
    out_path = CLIPS_OUTPUT / f"viz_{ts}_{safe_ticker}.mp4"

    render(
        portfolio=pv,
        hook=topic["hook"],
        final_line=final_line,
        events=topic.get("events", []),
        initial_investment=initial,
        output_path=out_path,
        audio_path=audio_path,
    )

    caption = _build_caption(topic)
    print("\n--- Caption preview ---")
    print(caption)
    print("--- End caption ---\n")

    if post:
        from uploader.instagram import publish
        try:
            url = publish(out_path, caption)
            log.info(f"Posted: {url}")
            print(f"✓ Posted: {url}")
        except Exception as e:
            log.error(f"Instagram upload failed: {e}")
            print(f"! Upload failed: {e}")

    log.info(f"=== Done: {out_path} ===")
    return out_path


def _build_caption(topic: dict) -> str:
    """Assemble the final Instagram caption from Claude's caption + hashtags + brand footer."""
    body = (topic.get("caption") or topic["hook"]).strip()
    body = body.replace("—", ",").replace("–", ",")  # kill em/en dashes (AI tells)

    raw_tags = topic.get("hashtags") or []
    tags = []
    for t in raw_tags:
        clean = re.sub(r"[^a-z0-9]", "", str(t).lower().lstrip("#"))
        if clean and clean not in tags:
            tags.append(clean)
    tags = tags[:6]
    hashtag_line = " ".join(f"#{t}" for t in tags)

    return f"{body}\n\n{BRAND_FOOTER}\n\n{hashtag_line}".strip()


def _reconcile_final_line(claude_line: str, actual_value: float) -> str:
    """Replace obviously-stale numbers in Claude's final line with the real value.
    Claude's training data is stale; the data is authoritative."""
    if not claude_line:
        return f"Worth ${actual_value:,.0f} today"
    # If the line contains a dollar amount, check it's within 2x of reality; else replace.
    m = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)", claude_line)
    if m:
        try:
            claude_val = float(m.group(1).replace(",", ""))
            if 0.5 * actual_value <= claude_val <= 2.0 * actual_value:
                return claude_line
        except ValueError:
            pass
    return f"Worth ${actual_value:,.0f} today"
