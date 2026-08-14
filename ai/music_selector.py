import base64
import os
from pathlib import Path
import anthropic

_client = None
CATEGORIES = ["hype_drop", "epic_buildup", "melancholic", "dark_phonk", "motivational"]

# Instagram music search queries per category
CATEGORY_QUERIES = {
    "hype_drop": "phonk trap",
    "epic_buildup": "epic cinematic",
    "melancholic": "sad emotional piano",
    "dark_phonk": "dark phonk",
    "motivational": "motivational uplifting",
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def select_music(clip: Path) -> tuple[str, str]:
    """Analyze clip visually, return (instagram_search_query, category)."""
    from processor.verify import _extract_frame, _get_duration

    dur = _get_duration(clip)
    try:
        frames = [_extract_frame(clip, dur * p) for p in [0.2, 0.5, 0.8]]
    except Exception as e:
        print(f"  Frame extract failed, defaulting to hype_drop: {e}")
        return CATEGORY_QUERIES["hype_drop"], "hype_drop"

    content = []
    for f in frames:
        b64 = base64.b64encode(f).decode()
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
    content.append({"type": "text", "text": (
        "Analyze this movie/TV clip. Choose the ONE best music category that fits its energy/mood.\n\n"
        "Categories:\n"
        "- hype_drop: hard-hitting phonk/EDM. For action, fights, chases, adrenaline.\n"
        "- epic_buildup: orchestral/cinematic. For dramatic reveals, hero moments, epic scenes.\n"
        "- melancholic: sad piano/emotional. For sad, tragic, reflective scenes.\n"
        "- dark_phonk: aggressive dark phonk. For villain scenes, sigma/menacing moments.\n"
        "- motivational: uplifting build. For training, victory, comeback moments.\n\n"
        "Respond with ONLY the category name — one word, lowercase, no punctuation."
    )})

    client = _get_client()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20,
        messages=[{"role": "user", "content": content}],
    )
    category = msg.content[0].text.strip().lower().split()[0]

    if category not in CATEGORIES:
        print(f"  Claude returned unknown category '{category}', defaulting to hype_drop")
        category = "hype_drop"

    print(f"  Music category: {category}")
    return CATEGORY_QUERIES[category], category
