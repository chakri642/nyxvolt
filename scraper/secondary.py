import json
import random
import shutil
from typing import Optional
import requests
from pathlib import Path
from config import CLIPS_PROCESSED, CLIPS_SECONDARY

FETCH_COUNT = 20
USED_CLIPS_FILE = Path(__file__).parent.parent / ".used_clips_brainrot.json"
MAX_USED_HISTORY = 300

KNOWN_GOOD_BRAINROT = [
    "subwaysurfers",
    "subwaysurfersgameplay",
    "minecraftparkourclips",
    "geometrydash.clips",
    "hydraulicpresschannel",
    "subwaysurferspov",
]


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


def _get_client():
    from uploader.instagram import _get_client as _ug
    return _ug()


def _fetch_cdn(url: str, dest: Path) -> Path:
    r = requests.get(url, stream=True, timeout=(8, 8))
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    r.close()
    return dest


def _download_and_verify() -> Optional[Path]:
    """Download one candidate brainrot clip and verify. Returns Path in CLIPS_PROCESSED, or None."""
    from ai.trending import suggest_brainrot_accounts
    from processor.verify import is_brainrot

    claude_accounts = suggest_brainrot_accounts()
    accounts = list(dict.fromkeys(claude_accounts + KNOWN_GOOD_BRAINROT))
    random.shuffle(accounts)
    print(f"  Trying {len(accounts)} brainrot accounts (Claude: {claude_accounts})")

    cl = _get_client()
    used = _load_used()
    print(f"  ({len(used)} brainrot clips in used history)")

    for attempt, username in enumerate(accounts[:12]):
        print(f"  Brainrot from @{username}...")
        try:
            user_id = cl.user_id_from_username(username)
            medias = cl.user_medias(user_id, amount=FETCH_COUNT)
            videos = [m for m in medias if m.media_type == 2 and str(m.pk) not in used]

            if not videos:
                print(f"  No unused videos on @{username}, trying next...")
                continue

            random.shuffle(videos)

            for media in videos[:5]:
                print(f"  Candidate: {media.like_count:,} likes | @{username} | code={media.code}")
                video_url = getattr(media, "video_url", None)
                if not video_url:
                    info = cl.media_info_v1(media.pk)
                    video_url = info.video_url
                dest = CLIPS_PROCESSED / f"secondary_{media.pk}.mp4"

                try:
                    _fetch_cdn(str(video_url), dest)
                except Exception as e:
                    print(f"    Download failed: {str(e)[:60]}")
                    continue

                if not (dest.exists() and dest.stat().st_size > 0):
                    continue

                if is_brainrot(dest):
                    print(f"    ✓ Verified as gameplay/crushing")
                    used.add(str(media.pk))
                    _save_used(used)
                    return dest
                else:
                    print(f"    ✗ Not gameplay, discarding")
                    used.add(str(media.pk))
                    dest.unlink(missing_ok=True)

            _save_used(used)

        except Exception as e:
            print(f"  Attempt {attempt + 1} failed ({str(e)[:70]}), retrying...")

    return None


def generate_pool(count: int):
    """Pre-generate `count` verified brainrot clips into CLIPS_SECONDARY folder."""
    CLIPS_SECONDARY.mkdir(parents=True, exist_ok=True)

    # Clear existing pool
    existing = list(CLIPS_SECONDARY.glob("pool_*.mp4"))
    for f in existing:
        f.unlink()
    if existing:
        print(f"Cleared {len(existing)} old pool clips")

    generated = 0
    max_attempts = count * 4
    for attempt in range(max_attempts):
        if generated >= count:
            break
        print(f"\n--- Attempt {attempt + 1} (pool {generated}/{count}) ---")
        try:
            clip = _download_and_verify()
            if clip:
                pool_path = CLIPS_SECONDARY / f"pool_{generated + 1}_{clip.stem}.mp4"
                shutil.move(str(clip), str(pool_path))
                generated += 1
                print(f"✓ Added to pool: {pool_path.name} ({generated}/{count})")
        except Exception as e:
            print(f"  Failed: {e}")

    print(f"\n{'='*50}")
    print(f"✓ Pool generation complete: {generated}/{count} clips ready")
    print(f"Location: {CLIPS_SECONDARY}")


def fetch_clip() -> Path:
    """Get a brainrot clip — reuse from pool if available, else download fresh."""
    pool = list(CLIPS_SECONDARY.glob("pool_*.mp4"))
    if pool:
        chosen = random.choice(pool)
        dest = CLIPS_PROCESSED / f"secondary_from_pool_{chosen.stem}.mp4"
        shutil.copy2(chosen, dest)
        print(f"  Using pool clip: {chosen.name} ({len(pool)} in pool)")
        return dest

    # No pool — download fresh
    print(f"  No pool clips available, downloading fresh...")
    clip = _download_and_verify()
    if not clip:
        raise RuntimeError("Could not download brainrot clip after trying all suggested accounts")
    return clip
