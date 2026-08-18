import logging
import re
import shutil
import time
from pathlib import Path

from config import BASE_DIR, CLIPS_OUTPUT
from ai_cinematic.concept import pick_concept, CLIP_LEN_SEC
from ai_cinematic.images import fetch_all
from ai_cinematic.motion import render_all
from ai_cinematic.stitch import render_hook_png, concat_clips, finalize
from ai_cinematic.voice import synthesize

log = logging.getLogger(__name__)

WORKDIR_ROOT = BASE_DIR / "clips" / "cinematic_scenes"
BRAND_FOOTER = "Daily AI cinematic edits by @nyxvolt"


def run(post: bool = False, keep_intermediates: bool = False, topic: str = None) -> Path:
    """Fully automated: concept -> images -> Ken Burns clips -> concat -> narration + subtitles -> hook overlay -> optional post.
    If `topic` is given, Claude builds the concept around that specific 'what if' idea instead of picking freely."""
    ts = int(time.time())
    workdir = WORKDIR_ROOT / f"run_{ts}"
    workdir.mkdir(parents=True, exist_ok=True)
    log.info(f"=== AI cinematic pipeline start (workdir={workdir}) ===")

    concept = pick_concept(user_topic=topic)

    image_paths = fetch_all(concept["image_prompts"], workdir / "images")
    clip_paths = render_all(concept["motions"], image_paths, CLIP_LEN_SEC, workdir / "clips")

    concat_path = workdir / "concat.mp4"
    concat_clips(clip_paths, concat_path)

    narration_text = _build_narration_text(concept["narration"])
    voice_path = workdir / "voice.mp3"
    srt_path = workdir / "voice.srt"
    synthesize(narration_text, voice_path, output_srt=srt_path)

    hook_png = workdir / "hook.png"
    render_hook_png(concept["hook"], hook_png)

    safe_niche = re.sub(r"[^a-zA-Z0-9_-]+", "_", concept.get("sub_niche", "clip"))[:30]
    out_path = CLIPS_OUTPUT / f"cine_{ts}_{safe_niche}.mp4"
    finalize(concat_path, hook_png, voice_path=voice_path, output_path=out_path, srt_path=srt_path)

    caption = _build_caption(concept)
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

    if not keep_intermediates:
        shutil.rmtree(workdir, ignore_errors=True)
        log.info(f"Cleaned workdir {workdir.name}")

    log.info(f"=== Done: {out_path} ===")
    return out_path


def _build_narration_text(narration: dict) -> str:
    """Combine hook + body + payoff into one continuous narration for edge-tts."""
    parts = [
        narration.get("hook_line", "").strip(),
        narration.get("body", "").strip(),
        narration.get("payoff", "").strip(),
    ]
    return " ".join(p.rstrip(".") + "." for p in parts if p)


def _build_caption(concept: dict) -> str:
    body = (concept.get("caption") or concept["hook"]).strip().replace("—", ",").replace("–", ",")
    raw_tags = concept.get("hashtags") or []
    tags = []
    for t in raw_tags:
        clean = re.sub(r"[^a-z0-9]", "", str(t).lower().lstrip("#"))
        if clean and clean not in tags:
            tags.append(clean)
    tags = tags[:6]
    hashtag_line = " ".join(f"#{t}" for t in tags)
    return f"{body}\n\n{BRAND_FOOTER}\n\n{hashtag_line}".strip()
