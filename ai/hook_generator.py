import base64
import os
import random
from pathlib import Path
import anthropic

_client = None

_STYLES = [
    "shock/disbelief (e.g. THIS SHOULD NOT BE POSSIBLE)",
    "curiosity gap (e.g. WAIT UNTIL YOU SEE THE END)",
    "hype (e.g. THIS BROKE THE INTERNET LAST WEEK)",
    "POV/immersion (e.g. POV YOU ARE WATCHING GREATNESS)",
    "superlative (e.g. THE CRAZIEST MOMENT OF THE YEAR)",
    "challenge (e.g. WATCH THIS UNTIL THE END)",
    "reaction (e.g. NO WAY HE ACTUALLY DID THAT)",
    "shock-value (e.g. YOU WONT BELIEVE WHAT HAPPENED NEXT)",
]


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def generate(category: str, clip_title: str = "") -> str:
    client = _get_client()
    style = random.choice(_STYLES)
    context = f'Clip title: "{clip_title}". ' if clip_title else ""
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=64,
        system=(
            "You write viral Instagram Reels hooks for entertainment content "
            "(MrBeast, iShowSpeed, movie clips, anime, sports highlights). "
            "Rules: exactly 5-7 words, ALL CAPS, no hashtags, no emojis, no punctuation except exclamation or ellipsis. "
            "Output ONLY the hook text, nothing else. Never repeat the same hook twice."
        ),
        messages=[{
            "role": "user",
            "content": f"{context}Category: {category}. Style: {style}. Write one hook."
        }],
    )
    return message.content[0].text.strip().upper()


def generate_from_video(clip: Path, title: str = "", transcript: str = "",
                        description: str = "", comments: list = None) -> str:
    """Analyze clip visually + use title/transcript/description/top-comments context.
    Top comments often reveal what viewers found emotionally striking — great for hooks."""
    from processor.verify import _extract_frame, _get_duration

    dur = _get_duration(clip)
    try:
        frames = [_extract_frame(clip, dur * p) for p in [0.15, 0.5, 0.85]]
    except Exception as e:
        print(f"  Hook frame extract failed: {e}")
        return "Wait for it"

    context_parts = []
    if title:
        context_parts.append(f"Video title: {title}")
    if description:
        context_parts.append(f"Video description (uploader's own words): {description[:600]}")
    if transcript:
        context_parts.append(f"Dialogue/subtitles from clip: {transcript[:600]}")
    if comments:
        top = "\n".join(f"- {c}" for c in comments[:8])
        context_parts.append(f"Top viewer comments (what people loved):\n{top}")
    context_block = "\n\n".join(context_parts)

    content = []
    for f in frames:
        b64 = base64.b64encode(f).decode()
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
    content.append({"type": "text", "text": (
        "You're writing a SCROLL-STOPPING HOOK for an Instagram Reel movie/TV edit.\n\n"
        f"{context_block}\n\n"
        "USE THE CONTEXT:\n"
        "- Top comments show what viewers found emotionally powerful — steal that emotion\n"
        "- Description often names the character/scene — use it for authenticity\n"
        "- Transcript is dialogue — DON'T quote it literally, but capture the vibe\n\n"
        "CRITICAL RULES:\n"
        "1. DO NOT literally describe what happens ('She asked for 5000', 'He shoots the guy')\n"
        "2. Create INTRIGUE, POV, emotion, or a bold claim — make people STOP scrolling\n"
        "3. Reference the character or vibe, not exact plot points\n"
        "4. 3-6 words maximum\n"
        "5. ASCII only. No emojis, no hashtags, no quotes\n\n"
        "GREAT hooks (mimic these):\n"
        "- 'POV you crossed him'\n"
        "- 'This is peak cinema'\n"
        "- 'The most sigma scene ever'\n"
        "- 'Watch how he handles this'\n"
        "- 'Why we rewatched it 10 times'\n"
        "- 'This character never missed'\n"
        "- 'Every villain wishes they were him'\n"
        "- 'The scene that broke us'\n"
        "- 'Chaos was always the plan'\n"
        "- 'The world made him this'\n\n"
        "BAD hooks (never write these):\n"
        "- 'She Asked For 5000' (literal description)\n"
        "- 'Cool Scene' (boring)\n"
        "- 'Watch This Video' (generic)\n\n"
        "Respond with ONLY the hook text. Nothing else."
    )})

    client = _get_client()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=30,
        messages=[{"role": "user", "content": content}],
    )
    hook = msg.content[0].text.strip().strip('"').strip("'")
    safe = "".join(c for c in hook if c.isalnum() or c in " .-!?,'")
    return safe[:60] or "Wait for it"
