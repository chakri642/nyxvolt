import json
import os
import random
import re
import requests
import yt_dlp
from pathlib import Path
from config import CLIPS_RAW, GAMES

MIN_DURATION = 30
MAX_DURATION = 600
MIN_VIEWS = 100_000
TOP_PICK_FROM = 10
USED_CLIPS_FILE = Path(__file__).parent.parent / ".used_yt_clips.json"
MAX_USED_HISTORY = 100

SKIP_TITLE_KEYWORDS = [
    "react", "irl", "just chatting", "talk", "podcast", "vlog",
    "unboxing", "setup", "face", "real life", "facecam",
    "cam", "room", "house", "eating", "cooking", "driving",
    "review", "tier list", "ranking", "tutorial", "how to",
]


def _load_used() -> set:
    if USED_CLIPS_FILE.exists():
        return set(json.loads(USED_CLIPS_FILE.read_text()))
    return set()


def _save_used(used: set):
    USED_CLIPS_FILE.write_text(json.dumps(list(used)[-MAX_USED_HISTORY:]))


def _search_videos(game: str, api_key: str) -> list[str]:
    resp = requests.get("https://www.googleapis.com/youtube/v3/search", params={
        "part": "snippet",
        "q": f"best {game} moments 2025",
        "type": "video",
        "videoDuration": "medium",
        "order": "viewCount",
        "maxResults": 50,
        "relevanceLanguage": "en",
        "regionCode": "US",
        "key": api_key,
    })
    resp.raise_for_status()
    return [
        item["id"]["videoId"]
        for item in resp.json().get("items", [])
        if item.get("id", {}).get("videoId")
    ]


def _get_video_details(video_ids: list[str], api_key: str) -> list[dict]:
    resp = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
        "part": "contentDetails,statistics,snippet",
        "id": ",".join(video_ids),
        "key": api_key,
    })
    resp.raise_for_status()
    return resp.json().get("items", [])


def _parse_duration(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _is_good_video(video: dict, used: set) -> bool:
    if video["id"] in used:
        return False
    if int(video.get("statistics", {}).get("viewCount", 0)) < MIN_VIEWS:
        return False
    duration = _parse_duration(video.get("contentDetails", {}).get("duration", "PT0S"))
    if not (MIN_DURATION <= duration <= MAX_DURATION):
        return False
    title_lower = video.get("snippet", {}).get("title", "").lower()
    if any(kw in title_lower for kw in SKIP_TITLE_KEYWORDS):
        return False
    return True


def download_clip(game: str = None) -> tuple[Path, str]:
    api_key = os.environ["YOUTUBE_API_KEY"]
    game = game or random.choice(GAMES)

    video_ids = _search_videos(game, api_key)
    if not video_ids:
        raise RuntimeError(f"No YouTube search results for: {game}")

    videos = _get_video_details(video_ids, api_key)
    used = _load_used()

    # Apply all quality filters
    quality = [v for v in videos if _is_good_video(v, used)]

    # Relax view filter if too strict
    if not quality:
        print("  Relaxing view filter...")
        quality = [
            v for v in videos
            if v["id"] not in used
            and MIN_DURATION <= _parse_duration(v.get("contentDetails", {}).get("duration", "PT0S")) <= MAX_DURATION
        ]
    if not quality:
        print("  Relaxing all filters, picking from top results...")
        quality = [
            v for v in videos
            if MIN_DURATION <= _parse_duration(v.get("contentDetails", {}).get("duration", "PT0S")) <= MAX_DURATION
        ]
    if not quality:
        quality = videos

    if not quality:
        raise RuntimeError(f"No valid YouTube clips found for: {game}")

    # Sort by views, pick randomly from top N
    quality.sort(key=lambda v: int(v.get("statistics", {}).get("viewCount", 0)), reverse=True)
    candidates = quality[:TOP_PICK_FROM]
    random.shuffle(candidates)

    cookie_path = Path(__file__).parent.parent / "youtube_cookies.txt"
    ydl_opts = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(CLIPS_RAW / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["ios", "android", "web"]}},
        **({"cookiefile": str(cookie_path)} if _valid_cookies(cookie_path) else {}),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for video in candidates:
            vid_id = video["id"]
            title = video.get("snippet", {}).get("title", "")
            view_count = int(video.get("statistics", {}).get("viewCount", 0))
            duration = _parse_duration(video.get("contentDetails", {}).get("duration", "PT0S"))
            print(f"  Trying: '{title}'")
            print(f"  Views: {view_count:,} | Duration: {duration}s")
            try:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid_id}", download=True)
                downloaded = Path(ydl.prepare_filename(info))
                if not downloaded.exists():
                    downloaded = downloaded.with_suffix(".mp4")
                if downloaded.exists() and downloaded.stat().st_size > 0:
                    used.add(vid_id)
                    _save_used(used)
                    return downloaded, game
            except Exception as e:
                print(f"  Skipping (error: {e!s:.80})")
                continue

    raise RuntimeError(f"All YouTube download attempts failed for: {game}")


def _valid_cookies(path: Path) -> bool:
    try:
        first_line = path.read_text().strip().splitlines()[0]
        return "Netscape HTTP Cookie File" in first_line
    except Exception:
        return False
