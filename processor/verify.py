import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
import anthropic

_client = None
FRAME_PERCENTS = [0.10, 0.35, 0.60, 0.85]


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _get_duration(path: Path) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)
    ], capture_output=True, text=True)
    try:
        for stream in json.loads(result.stdout).get("streams", []):
            if stream.get("codec_type") == "video":
                return float(stream.get("duration", 30))
    except Exception:
        pass
    return 30.0


def _extract_frame(video: Path, timestamp: float) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        subprocess.run([
            "ffmpeg", "-y", "-ss", f"{timestamp:.2f}", "-i", str(video),
            "-frames:v", "1", "-q:v", "3",
            "-vf", "scale=540:-1",  # scale down to reduce vision token cost
            str(tmp_path)
        ], capture_output=True, check=True, timeout=30)
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def is_brainrot(clip: Path) -> bool:
    """3-frame check — is the ENTIRE clip actually gameplay/crushing content?"""
    duration = _get_duration(clip)
    try:
        # Check start, middle, end — catches clips that mix gameplay with promo/menu screens
        frames = [_extract_frame(clip, duration * pct) for pct in [0.20, 0.50, 0.80]]
    except Exception:
        return False

    content = []
    for frame in frames:
        b64 = base64.b64encode(frame).decode()
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
        })
    content.append({"type": "text", "text": (
        "Are ALL 3 frames showing PURE gameplay/crushing content? "
        "Valid = active game screen recording (Subway Surfers running, Minecraft parkour, "
        "Geometry Dash) OR hydraulic press crushing OR satisfying crush/cut videos. "
        "INVALID = character-select screens, menus, promo/unlock cards, static screens, "
        "people talking, reactions, cartoons, memes, trailers, real-life parkour. "
        "Answer ONLY 'YES' if all 3 are pure gameplay/crushing, else 'NO'."
    )})

    client = _get_client()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=20,
        messages=[{"role": "user", "content": content}],
    )
    return "yes" in msg.content[0].text.strip().lower()[:5]


def verify(video: Path, category: str, hook: str, brainrot: bool) -> dict[str, Any]:
    duration = _get_duration(video)
    timestamps = [duration * p for p in FRAME_PERCENTS]

    frames = []
    for ts in timestamps:
        try:
            frames.append(_extract_frame(video, ts))
        except Exception as e:
            print(f"  Frame extract failed at {ts:.1f}s: {e}")

    if not frames:
        return {"pass": False, "issues": ["Could not extract any frames"], "notes": "verify skipped"}

    content = []
    for frame_bytes in frames:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(frame_bytes).decode(),
            },
        })

    layout_desc = (
        "vertical 1080x1920 split-screen. TOP HALF is the main content, "
        "BOTTOM HALF is 'brainrot' (mobile game gameplay or crushing videos)."
    ) if brainrot else "vertical 1080x1920 single video (no split-screen)."

    prompt = (
        f"You're verifying an auto-generated Instagram Reel. The intended category was '{category}' but "
        "ANY viral entertainment content (movie trailers, animations, sports, music videos, celebrities, "
        "memes, action clips) is FINE — don't reject just because it doesn't literally match the category label.\n\n"
        f"Video layout: {layout_desc}\n\n"
        "REJECT ONLY IF:\n"
        "1. Main content has spoken/written text clearly in a NON-ENGLISH language "
        "(Hindi, Arabic, Chinese, Punjabi, Spanish subtitles etc.). "
        "Movie trailers, music videos, and pure visual content without language are FINE.\n"
        + ("2. BRAINROT (bottom half) is clearly NOT gameplay/crushing — e.g., people talking to camera, "
           "reactions, dancing, memes, cartoons, tutorials, collages of multiple people.\n"
           "3. BRAINROT is stuck on a menu/character-select/promo screen for most of the clip "
           "(brief transitions between gameplay are OK).\n"
           if brainrot else "")
        + "4. Serious visual glitches: heavy distortion, freeze frames, watermarks blocking most of the frame.\n"
        "5. THIRD-PARTY CREATOR/CHANNEL WATERMARKS baked into the video — text overlays like "
        "'NQ FILMS', 'CINEMA CLIPS', 'MOVIE MOMENTS', channel handles/logos, or any YouTube/TikTok "
        "creator branding on top of the movie footage. These make the repost look stolen and hurt the account. "
        "Small studio logos (Warner Bros, Marvel, Netflix corner logos) belonging to the ORIGINAL film are FINE.\n\n"
        "APPROVE:\n"
        "- Movie trailers / cinematic clips even if animated (Despicable Me, Marvel etc.)\n"
        "- Sports, music, celebrities, memes, viral clips of any type\n"
        "- Content with English text OR content that's language-agnostic (visuals + music only)\n"
        "- Brainrot showing real gameplay/crushing with minor UI or brief moments of non-action\n"
        "- Content with only the original studio's logo (not third-party creator watermarks)\n\n"
        "Return ONLY valid JSON, no other text:\n"
        '{"pass": true|false, "issues": ["specific problems"], "notes": "1-line assessment"}\n'
    )

    content.append({"type": "text", "text": prompt})

    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": content}],
    )

    raw = message.content[0].text
    import re
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"pass": False, "issues": ["Could not parse verifier response"], "notes": raw[:200]}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"pass": False, "issues": ["Could not parse verifier response"], "notes": raw[:200]}
