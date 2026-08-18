import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

OUT_W = 1080
OUT_H = 1920
FPS = 30

# ffmpeg zoompan filter formulas per motion type.
# `on` = output frame number, `d` = duration in frames - 1.
# Zoom > 1 always so pan motion has room; source is 1440x2560 (33% headroom).
_MOTIONS = {
    "zoom_in":   {"z": "1.0+0.20*on/{d}",  "x": "iw/2-(iw/zoom/2)",         "y": "ih/2-(ih/zoom/2)"},
    "zoom_out":  {"z": "1.20-0.20*on/{d}", "x": "iw/2-(iw/zoom/2)",         "y": "ih/2-(ih/zoom/2)"},
    "pan_left":  {"z": "1.15",             "x": "(iw-iw/zoom)*(1-on/{d})", "y": "ih/2-(ih/zoom/2)"},
    "pan_right": {"z": "1.15",             "x": "(iw-iw/zoom)*(on/{d})",   "y": "ih/2-(ih/zoom/2)"},
    "pan_up":    {"z": "1.15",             "x": "iw/2-(iw/zoom/2)",         "y": "(ih-ih/zoom)*(1-on/{d})"},
    "pan_down":  {"z": "1.15",             "x": "iw/2-(iw/zoom/2)",         "y": "(ih-ih/zoom)*(on/{d})"},
}


def render_scene(image_path: Path, motion: str, duration_sec: float, output_path: Path) -> Path:
    """Render one still image with Ken Burns motion into a 1080x1920 mp4 clip."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_frames = int(duration_sec * FPS)
    d_minus_1 = max(total_frames - 1, 1)

    m = _MOTIONS.get(motion, _MOTIONS["zoom_in"])
    z_expr = m["z"].format(d=d_minus_1)
    x_expr = m["x"].format(d=d_minus_1)
    y_expr = m["y"].format(d=d_minus_1)

    vf = (
        f"scale=w={OUT_W * 2}:h={OUT_H * 2}:force_original_aspect_ratio=increase,"
        f"crop={OUT_W * 2}:{OUT_H * 2},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={OUT_W}x{OUT_H}:fps={FPS}"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", vf,
        "-t", f"{duration_sec}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "fast", "-crf", "20",
        "-r", str(FPS),
        str(output_path),
    ]
    log.info(f"Rendering {motion} {duration_sec}s: {image_path.name} -> {output_path.name}")
    subprocess.run(cmd, check=True)
    return output_path


def render_all(motions: list, image_paths: list, duration_sec: float, output_dir: Path) -> list:
    """Render every image with its paired motion into its own clip."""
    if len(motions) != len(image_paths):
        raise ValueError(f"motions ({len(motions)}) and image_paths ({len(image_paths)}) length mismatch")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, (motion, img) in enumerate(zip(motions, image_paths)):
        clip_path = output_dir / f"clip_{i + 1}.mp4"
        render_scene(img, motion, duration_sec, clip_path)
        clips.append(clip_path)
    return clips
