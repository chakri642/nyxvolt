import json
import os
import time
from pathlib import Path
from typing import Optional
from instagrapi import Client
from instagrapi.exceptions import ClientError

_client = None
_SESSION_FILE = Path(__file__).parent.parent / ".instagram_session.json"


def _get_client(force_fresh: bool = False) -> Client:
    global _client
    if _client and not force_fresh:
        return _client

    cl = Client()
    cl.delay_range = [3, 8]  # slightly longer to look less automated

    if _SESSION_FILE.exists() and not force_fresh:
        try:
            cl.load_settings(_SESSION_FILE)
            cl.login(
                os.environ["INSTAGRAM_USERNAME"],
                os.environ["INSTAGRAM_PASSWORD"],
            )
            _client = cl
            return _client
        except Exception:
            _SESSION_FILE.unlink(missing_ok=True)

    cl.login(
        os.environ["INSTAGRAM_USERNAME"],
        os.environ["INSTAGRAM_PASSWORD"],
    )
    cl.dump_settings(_SESSION_FILE)
    _client = cl
    return _client


def _find_track(query: str) -> Optional[str]:
    """Search Instagram's music library, return track ID or None."""
    try:
        cl = _get_client()
        tracks = cl.music_search(query, product_type="clips")
        if tracks:
            track = tracks[0]
            track_id = getattr(track, "id", None) or getattr(track, "track_id", None)
            if track_id:
                print(f"  Instagram music: '{getattr(track, 'title', query)}' (id={track_id})")
                return str(track_id)
    except Exception as e:
        print(f"  Music search failed ({e}), uploading without soundtrack")
    return None


def publish(video: Path, caption: str, music_query: str = None, retries: int = 2) -> str:
    extra_data = {}
    if music_query:
        track_id = _find_track(music_query)
        if track_id:
            extra_data["clips_audio_metadata"] = json.dumps({"music_canonical_id": track_id})

    for attempt in range(retries + 1):
        try:
            cl = _get_client(force_fresh=(attempt > 0))
            media = cl.clip_upload(video, caption=caption, extra_data=extra_data)
            return f"https://www.instagram.com/p/{media.code}/"
        except ClientError as e:
            err_msg = str(e)[:200]
            print(f"  Upload attempt {attempt + 1} failed: {err_msg}")
            if attempt < retries:
                _SESSION_FILE.unlink(missing_ok=True)
                global _client
                _client = None
                time.sleep(15)
            else:
                raise
