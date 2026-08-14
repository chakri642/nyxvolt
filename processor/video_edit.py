import json
import subprocess
from pathlib import Path
from config import (
    CLIPS_PROCESSED, OUTPUT_WIDTH, OUTPUT_HEIGHT, OUTPUT_FPS,
    SPEED_FACTOR, SATURATION, CONTRAST, FLASH_DURATION,
)


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


def transform(source: Path) -> Path:
    duration = _get_duration(source)
    output = CLIPS_PROCESSED / f"{source.stem}_transformed.mp4"

    fade_out_start = max(0.0, (duration / SPEED_FACTOR) - FLASH_DURATION)

    filter_complex = (
        # Background: speed → color → scale to fill → crop → blur → darken
        f"[0:v]setpts=PTS/{SPEED_FACTOR},"
        f"eq=saturation={SATURATION}:contrast={CONTRAST},"
        f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
        f"boxblur=25:5,eq=brightness=-0.15[bg];"

        # Foreground: speed → color → scale to fit width
        f"[0:v]setpts=PTS/{SPEED_FACTOR},"
        f"eq=saturation={SATURATION}:contrast={CONTRAST},"
        f"scale={OUTPUT_WIDTH}:-2:force_original_aspect_ratio=decrease[fg];"

        # Overlay fg centered on bg + fades
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"fade=t=in:st=0:d={FLASH_DURATION},"
        f"fade=t=out:st={fade_out_start}:d={FLASH_DURATION}[v];"

        # Audio: speed
        f"[0:a]atempo={SPEED_FACTOR}[a]"
    )

    cmd = [
        "ffmpeg", "-y", "-i", str(source),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-r", str(OUTPUT_FPS),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output),
    ]
    _run(cmd)
    return output


def _run(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")
