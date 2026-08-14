import json
import os
import random
import re
import time
import requests
import yt_dlp
from pathlib import Path
from config import CLIPS_RAW

MIN_VIEWS = 500_000
MIN_DURATION = 20
MAX_DURATION = 180
TOP_PICK_FROM = 5

USED_CLIPS_FILE = Path(__file__).parent.parent / ".used_clips_movies.json"
CANDIDATES_CACHE_FILE = Path(__file__).parent.parent / ".movie_candidates_cache.json"
COOKIE_FILE = Path(__file__).parent.parent / "youtube_cookies.txt"
CACHE_TTL_HOURS = 24
MAX_USED_HISTORY = 300

SKIP_KEYWORDS = [
    "full movie", "trailer", "official", "interview", "behind the scenes",
    "making of", "reaction", "review", "explained", "podcast", "commentary",
    "compilation hours", "all scenes",
]

# Fallback video IDs (known viral movie edits) — used if YouTube API quota is exhausted
FALLBACK_VIDEO_IDS = [
    ("ldKcPuHOOI4", "PEAKY BLINDERS - YOU DIDN'T NEED ALL THEM TABLETS", 171_000_000),
    ("flJOutKwIr4", "Joker whatsapp status 4k", 160_000_000),
    ("VPaKPnVsTO8", "Gustavo's Revenge - Breaking Bad", 114_000_000),
    ("4QenPnBk99M", "Is there any man here named Shelby - Peaky Blinders", 88_000_000),
    ("krQHQvtIr6w", "Rick Grimes vs Walter White", 82_000_000),
    ("HQAzGmZmbH0", "Peaky Blinders Sniper Target Practice", 72_000_000),
    ("n2qlqtVfkwg", "Tommy roasting Campbell - Peaky Blinders", 69_000_000),
    ("cu-rkCWMwyc", "Bruce Wayne Edit - 2 Million Dollars", 58_000_000),
    ("WkEQhUMs77Y", "Walter's transformation - Breaking Bad", 56_000_000),
    ("y6LVbVCMozo", "Joker Sad Moment 4k", 53_000_000),
]


def _load_used() -> set:
    if USED_CLIPS_FILE.exists():
        try:
            return set(json.loads(USED_CLIPS_FILE.read_text()))
        except Exception:
            pass
    return set()


def _save_used(used: set):
    USED_CLIPS_FILE.write_text(json.dumps(list(used)[-MAX_USED_HISTORY:]))


def _load_candidates_cache() -> list:
    """Load cached candidates if fresh (< 24h old), else return empty list."""
    if not CANDIDATES_CACHE_FILE.exists():
        return []
    try:
        cache = json.loads(CANDIDATES_CACHE_FILE.read_text())
        age_hours = (time.time() - cache.get("timestamp", 0)) / 3600
        if age_hours > CACHE_TTL_HOURS:
            print(f"  Cache stale ({age_hours:.1f}h old), refreshing")
            return []
        candidates = cache.get("candidates", [])
        print(f"  Using candidate cache ({len(candidates)} clips, {age_hours:.1f}h old)")
        return candidates
    except Exception:
        return []


def _save_candidates_cache(candidates: list):
    CANDIDATES_CACHE_FILE.write_text(json.dumps({
        "timestamp": time.time(),
        "candidates": candidates,
    }))


def _parse_duration(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _search_youtube(query: str, api_key: str) -> list[dict]:
    resp = requests.get("https://www.googleapis.com/youtube/v3/search", params={
        "part": "snippet",
        "q": query,
        "type": "video",
        "videoDuration": "short",
        "order": "viewCount",
        "maxResults": 20,
        "relevanceLanguage": "en",
        "regionCode": "US",
        "key": api_key,
    }, timeout=10)
    resp.raise_for_status()
    ids = [item["id"]["videoId"] for item in resp.json().get("items", []) if item.get("id", {}).get("videoId")]
    if not ids:
        return []
    details = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
        "part": "contentDetails,statistics,snippet",
        "id": ",".join(ids),
        "key": api_key,
    }, timeout=10)
    details.raise_for_status()
    return details.json().get("items", [])


def _is_good(video: dict, used: set) -> bool:
    if video["id"] in used:
        return False
    if int(video.get("statistics", {}).get("viewCount", 0)) < MIN_VIEWS:
        return False
    dur = _parse_duration(video.get("contentDetails", {}).get("duration", "PT0S"))
    if not (MIN_DURATION <= dur <= MAX_DURATION):
        return False
    title = video.get("snippet", {}).get("title", "").lower()
    if any(kw in title for kw in SKIP_KEYWORDS):
        return False
    return True


def _valid_cookies(path: Path) -> bool:
    try:
        return "Netscape HTTP Cookie File" in path.read_text().strip().splitlines()[0]
    except Exception:
        return False


def _build_ydl_opts() -> dict:
    """Configure yt-dlp with cookies (file → browser → clientless fallback)."""
    if _valid_cookies(COOKIE_FILE):
        print(f"  Using cookie file: {COOKIE_FILE.name}")
        auth = {"cookiefile": str(COOKIE_FILE)}
    else:
        # Try to pull from installed browsers automatically
        print("  No cookie file found; trying browser cookies (chrome → safari → firefox)")
        auth = {"cookiesfrombrowser": ("chrome",)}

    return {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(CLIPS_RAW / "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["ios", "android"]}},
        **auth,
    }


def get_transcript(video_id: str, rapid_key: str = None) -> str:
    """Fetch transcript via yt-dlp subtitles. Returns dialogue text or empty string."""
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en"],
            "skip_download": True,
            "subtitlesformat": "vtt",
        }
        if _valid_cookies(COOKIE_FILE):
            ydl_opts["cookiefile"] = str(COOKIE_FILE)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            subs = info.get("subtitles") or info.get("automatic_captions") or {}
            en_tracks = subs.get("en") or subs.get("en-US") or subs.get("en-GB") or []
            if not en_tracks:
                return ""
            # Fetch VTT text
            vtt_url = en_tracks[-1].get("url")
            if not vtt_url:
                return ""
            resp = requests.get(vtt_url, timeout=10)
            resp.raise_for_status()
            # Strip VTT timestamps + tags, keep dialogue only
            lines = []
            for line in resp.text.splitlines():
                if "-->" in line or line.strip().isdigit() or not line.strip():
                    continue
                if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                    continue
                lines.append(re.sub(r"<[^>]+>", "", line).strip())
            return " ".join(l for l in lines if l)[:1500]
    except Exception as e:
        print(f"  Transcript fetch failed: {str(e)[:80]}")
        return ""


def download_clip() -> tuple[Path, str]:
    from ai.trending import suggest_movie_queries
    api_key = os.environ["YOUTUBE_API_KEY"]

    try:
        queries = suggest_movie_queries()
    except Exception as e:
        print(f"  Claude query suggestion failed: {e}")
        queries = []

    fallback_queries = [
        "joker edit 4k", "thomas shelby sigma edit", "walter white best scenes",
        "dark knight best scenes 4k", "breaking bad sigma edit",
    ]
    all_queries = list(dict.fromkeys(queries + fallback_queries))
    random.shuffle(all_queries)

    used = _load_used()

    # Try candidate cache first (preserve YouTube API quota)
    cached = _load_candidates_cache()
    cached = [c for c in cached if c.get("id") not in used]

    if len(cached) >= 5:
        unique = cached
    else:
        print(f"  Cache thin — searching YouTube ({len(all_queries)} queries)")
        candidates = []
        for query in all_queries[:6]:
            try:
                videos = _search_youtube(query, api_key)
                good = [v for v in videos if _is_good(v, used)]
                top_views = sorted([int(v.get("statistics", {}).get("viewCount", 0)) for v in good], reverse=True)[:3]
                print(f"  '{query}': {len(good)} good | top views: {[f'{v//1000}K' for v in top_views]}")
                candidates.extend(good)
            except Exception as e:
                print(f"  Query failed ({query[:40]}): {str(e)[:60]}")

        if not candidates:
            print("  YouTube API exhausted — using hardcoded fallback list")
            candidates = [
                {
                    "id": vid,
                    "snippet": {"title": title},
                    "statistics": {"viewCount": str(views)},
                    "contentDetails": {"duration": "PT1M"},
                }
                for vid, title, views in FALLBACK_VIDEO_IDS
                if vid not in used
            ]
            if not candidates:
                raise RuntimeError("No fallback clips available (all in used history)")

        candidates.sort(key=lambda v: int(v.get("statistics", {}).get("viewCount", 0)), reverse=True)
        seen, unique = set(), []
        for v in candidates:
            if v["id"] not in seen:
                seen.add(v["id"])
                unique.append(v)
        _save_candidates_cache(unique[:30])

    top = unique[:TOP_PICK_FROM]
    top_views = [f"{int(v['statistics']['viewCount'])//1000}K" for v in top]
    print(f"  Top {len(top)} candidates | views: {top_views}")

    ydl_opts = _build_ydl_opts()

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for video in top:
            vid_id = video["id"]
            title = video["snippet"]["title"]
            views = int(video["statistics"]["viewCount"])
            dur = _parse_duration(video["contentDetails"]["duration"])
            print(f"  Trying: '{title}' | {views//1000}K views | {dur}s")
            try:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid_id}", download=True)
                downloaded = Path(ydl.prepare_filename(info))
                if not downloaded.exists():
                    downloaded = downloaded.with_suffix(".mp4")
                if downloaded.exists() and downloaded.stat().st_size > 0:
                    size_mb = downloaded.stat().st_size / (1024 * 1024)
                    print(f"    Downloaded: {size_mb:.1f} MB")
                    used.add(vid_id)
                    _save_used(used)
                    return downloaded, title[:60]
            except Exception as e:
                print(f"  Skipping ({str(e)[:100]})")

    raise RuntimeError("All YouTube download attempts failed — cookies may have expired")
