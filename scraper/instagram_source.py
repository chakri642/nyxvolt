import json
import random
import re
import requests
from pathlib import Path
from config import CLIPS_RAW

FETCH_COUNT = 25  # more variety per account
USED_CLIPS_FILE = Path(__file__).parent.parent / ".used_clips_main.json"
MAX_USED_HISTORY = 300


def _load_used() -> set:
    if USED_CLIPS_FILE.exists():
        try:
            return set(json.loads(USED_CLIPS_FILE.read_text()))
        except Exception:
            pass
    return set()


def _save_used(used: set):
    trimmed = list(used)[-MAX_USED_HISTORY:]
    USED_CLIPS_FILE.write_text(json.dumps(trimmed))

SKIP_KEYWORDS = [
    "ad", "promo", "sponsor", "link in bio", "swipe up",
    "dm me", "check out my", "shop now",
]

ENGLISH_FUNCTION_WORDS = {
    "the", "and", "you", "your", "is", "are", "was", "were", "this",
    "that", "of", "in", "on", "to", "for", "with", "at", "by", "from",
    "have", "has", "had", "do", "does", "did", "can", "will", "would",
    "not", "or", "as", "an", "a", "but", "if", "when", "how", "why",
    "what", "where", "which", "who", "it", "its", "there", "then",
    "them", "they", "we", "our",
}


def _get_client():
    from uploader.instagram import _get_client as _ug
    return _ug()


def _is_english(caption: str) -> bool:
    if not caption or len(caption.strip()) < 15:
        return True
    text = caption.lower()
    non_ascii = sum(1 for c in caption if ord(c) > 127 and not (0x1F300 <= ord(c) <= 0x1FAFF))
    if non_ascii > 10:
        return False
    words = set(re.findall(r"\b[a-z]+\b", text))
    if len(words) >= 5:
        if len(words & ENGLISH_FUNCTION_WORDS) < 2:
            return False
    return True


def _fetch_cdn(url: str, dest: Path) -> Path:
    r = requests.get(url, stream=True, timeout=(8, 8))
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    r.close()
    return dest


def download_clip(game: str = None) -> tuple[Path, str]:
    from ai.trending import suggest_accounts
    suggestion = suggest_accounts(game)
    entries = suggestion["accounts"]  # list of {username, category}

    # Shuffle so we don't always hit the same one first
    random.shuffle(entries)
    print(f"  Got {len(entries)} diverse trending accounts from Claude")

    cl = _get_client()
    used = _load_used()
    print(f"  ({len(used)} main clips in used history)")

    for attempt, entry in enumerate(entries[:12]):
        username = entry["username"]
        category = entry["category"]
        print(f"  Fetching from @{username} ({category})...")

        try:
            user_id = cl.user_id_from_username(username)
            medias = cl.user_medias(user_id, amount=FETCH_COUNT)

            all_videos = [m for m in medias if m.media_type == 2 and str(m.pk) not in used]
            top_likes = sorted([m.like_count or 0 for m in all_videos], reverse=True)[:5]
            print(f"  Pool: {len(all_videos)} unused videos | top 5 likes: {top_likes}")

            videos = [
                m for m in all_videos
                if (m.like_count or 0) >= 100_000
                and _is_english(m.caption_text or "")
                and not any(kw in (m.caption_text or "").lower() for kw in SKIP_KEYWORDS)
            ]
            if not videos:
                videos = [
                    m for m in all_videos
                    if (m.like_count or 0) >= 25_000
                    and _is_english(m.caption_text or "")
                    and not any(kw in (m.caption_text or "").lower() for kw in SKIP_KEYWORDS)
                ]
            if not videos:
                print(f"  No qualifying unused video from @{username}, trying next account...")
                continue

            random.shuffle(videos)
            media = videos[0]
            print(f"  Selected: {media.like_count:,} likes | @{username} | code={media.code}")

            # Use video_url from media object first — avoids the throttled media_info_v1 endpoint
            video_url = getattr(media, "video_url", None)
            if not video_url:
                info = cl.media_info_v1(media.pk)
                video_url = info.video_url
            dest = CLIPS_RAW / f"{media.pk}.mp4"
            _fetch_cdn(str(video_url), dest)

            if dest.exists() and dest.stat().st_size > 0:
                used.add(str(media.pk))
                _save_used(used)
                return dest, category

        except Exception as e:
            print(f"  Attempt {attempt + 1} failed ({str(e)[:70]})")

    raise RuntimeError("Could not download main clip after trying all suggested accounts")
