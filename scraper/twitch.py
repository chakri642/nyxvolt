import json
import os
import random
import requests
import yt_dlp
from pathlib import Path
from config import CLIPS_RAW, TWITCH_GAME_IDS

MIN_DURATION = 25
MAX_DURATION = 90
MIN_VIEWS = 30000
TOP_PICK_FROM = 10
USED_CLIPS_FILE = Path(__file__).parent.parent / ".used_clips.json"
MAX_USED_HISTORY = 100

# Words in titles that indicate non-gameplay (facecam/react/IRL) content
SKIP_TITLE_KEYWORDS = [
    "react", "irl", "just chatting", "talk", "podcast", "vlog",
    "unboxing", "setup", "face", "real life", "facecam",
    "cam", "room", "house", "eating", "cooking", "driving",
]


def _get_token() -> str:
    resp = requests.post("https://id.twitch.tv/oauth2/token", params={
        "client_id": os.environ["TWITCH_CLIENT_ID"],
        "client_secret": os.environ["TWITCH_CLIENT_SECRET"],
        "grant_type": "client_credentials",
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def _load_used() -> set:
    if USED_CLIPS_FILE.exists():
        return set(json.loads(USED_CLIPS_FILE.read_text()))
    return set()


def _save_used(used: set):
    USED_CLIPS_FILE.write_text(json.dumps(list(used)[-MAX_USED_HISTORY:]))


def _is_good_clip(clip: dict, used: set) -> bool:
    if clip["id"] in used:
        return False
    if clip.get("view_count", 0) < MIN_VIEWS:
        return False
    duration = clip.get("duration", 0)
    if not (MIN_DURATION <= duration <= MAX_DURATION):
        return False
    if clip.get("language", "en") not in ("en", ""):
        return False
    title_lower = clip.get("title", "").lower()
    if any(kw in title_lower for kw in SKIP_TITLE_KEYWORDS):
        return False
    return True


def download_clip(game: str = None) -> tuple[Path, str, str]:
    game = game or random.choice(list(TWITCH_GAME_IDS.keys()))
    game_id = TWITCH_GAME_IDS.get(game)
    if not game_id:
        game = random.choice(list(TWITCH_GAME_IDS.keys()))
        game_id = TWITCH_GAME_IDS[game]

    token = _get_token()
    headers = {
        "Client-ID": os.environ["TWITCH_CLIENT_ID"],
        "Authorization": f"Bearer {token}",
    }

    # Try last 7 days first (trending), fall back to last 90 days
    clips = []
    for days in [7, 30, 90]:
        params = {"game_id": game_id, "first": 100}
        if days < 90:
            params["started_at"] = _days_ago(days)
        resp = requests.get("https://api.twitch.tv/helix/clips", headers=headers, params=params)
        resp.raise_for_status()
        clips = resp.json().get("data", [])
        high_view = [c for c in clips if c.get("view_count", 0) >= MIN_VIEWS]
        if len(high_view) >= 5:
            break

    used = _load_used()

    # Apply all quality filters
    quality_clips = [c for c in clips if _is_good_clip(c, used)]

    # Relax filters progressively if too strict
    if not quality_clips:
        print("  Relaxing view filter...")
        quality_clips = [
            c for c in clips
            if c["id"] not in used
            and MIN_DURATION <= c.get("duration", 0) <= MAX_DURATION
            and c.get("language", "en") in ("en", "")
        ]
    if not quality_clips:
        print("  Relaxing all filters, picking from top clips...")
        quality_clips = [
            c for c in clips
            if MIN_DURATION <= c.get("duration", 0) <= MAX_DURATION
        ]
    if not quality_clips:
        quality_clips = clips

    if not quality_clips:
        raise RuntimeError(f"No Twitch clips found for game: {game}")

    # Sort by views, pick randomly from top N
    quality_clips.sort(key=lambda c: c.get("view_count", 0), reverse=True)
    clip = random.choice(quality_clips[:TOP_PICK_FROM])
    title = clip.get("title", "")

    print(f"  Selected: '{title}'")
    print(f"  Views: {clip.get('view_count', 0):,} | Duration: {clip.get('duration', 0)}s | Language: {clip.get('language', 'en')}")

    output_path = CLIPS_RAW / "%(id)s.%(ext)s"
    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(output_path),
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(clip["url"], download=True)
        downloaded = Path(ydl.prepare_filename(info))

    used.add(clip["id"])
    _save_used(used)

    return downloaded, game, title


def _days_ago(days: int) -> str:
    from datetime import datetime, timedelta, timezone
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
