import json
import random
import subprocess
from pathlib import Path
from config import (
    CLIPS_PROCESSED, OUTPUT_WIDTH, OUTPUT_HEIGHT,
    SPEED_FACTOR, SATURATION, CONTRAST,
)


def _get_duration(path: Path) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)
    ], capture_output=True, text=True)
    try:
        for stream in json.loads(result.stdout).get("streams", []):
            if stream.get("codec_type") == "video":
                return float(stream.get("duration", 60))
    except Exception:
        pass
    return 60.0


def composite(main: Path) -> Path:
    """Split-screen: top = main clip (blur-fill), bottom = brainrot clip (blur-fill).
    Both halves show the ENTIRE clip centered on a blurred version of itself — no cropping loss."""
    from scraper.secondary import fetch_clip
    secondary = fetch_clip()

    output = CLIPS_PROCESSED / f"{main.stem}_brainrot.mp4"

    w = OUTPUT_WIDTH
    half_h = OUTPUT_HEIGHT // 2

    # Both halves use blur-bg + centered fit — preserves full clip content
    filter_complex = (
        # === TOP HALF: main clip with speed + color effects + blur-fill ===
        f"[0:v]setpts=PTS/{SPEED_FACTOR},"
        f"eq=saturation={SATURATION}:contrast={CONTRAST},split=2[top_bg_src][top_fg_src];"
        f"[top_bg_src]scale={w}:{half_h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{half_h},boxblur=25:5,eq=brightness=-0.25[top_bg];"
        f"[top_fg_src]scale={w}:{half_h}:force_original_aspect_ratio=decrease[top_fg];"
        f"[top_bg][top_fg]overlay=(W-w)/2:(H-h)/2[top];"

        # === BOTTOM HALF: brainrot clip with blur-fill ===
        f"[1:v]split=2[bot_bg_src][bot_fg_src];"
        f"[bot_bg_src]scale={w}:{half_h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{half_h},boxblur=25:5,eq=brightness=-0.25[bot_bg];"
        f"[bot_fg_src]scale={w}:{half_h}:force_original_aspect_ratio=decrease[bot_fg];"
        f"[bot_bg][bot_fg]overlay=(W-w)/2:(H-h)/2[bot];"

        # === STACK ===
        f"[top][bot]vstack=inputs=2[v];"

        # === AUDIO: main audio, sped up to match video ===
        f"[0:a]atempo={SPEED_FACTOR}[a]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(main),
        "-stream_loop", "-1", "-i", str(secondary),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-shortest",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output),
    ]
    print(f"  Running ffmpeg split-screen (secondary={secondary.name})...")
    _run(cmd)
    return output


def _run(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg split-screen failed:\n{result.stderr[-2000:]}")
