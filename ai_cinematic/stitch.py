import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

W, H = 1080, 1920
HOOK_HOLD_SEC = 2.5
HOOK_FADE_SEC = 0.4


def _find_font(size: int) -> ImageFont.FreeTypeFont:
    """Try a few common macOS bold fonts, fall back to PIL default."""
    for path in (
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, max_chars: int) -> List[str]:
    """Simple greedy word-wrap so the hook fits inside the frame."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_hook_png(hook: str, output_path: Path) -> Path:
    """Render the hook as a bold-white-on-transparent PNG the size of the video."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    lines = _wrap_text(hook, max_chars=22)
    fontsize = 76 if len(lines) <= 2 else 62
    font = _find_font(fontsize)

    line_h = int(fontsize * 1.15)
    total_h = line_h * len(lines)
    y = int(H * 0.12)

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (W - w) // 2
        # black outline for readability on any background
        for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-3, -3), (3, 3), (-3, 3), (3, -3)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 220))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h

    # Small watermark bottom-right
    wm_font = _find_font(28)
    wm_text = "@nyxvolt"
    wbbox = draw.textbbox((0, 0), wm_text, font=wm_font)
    wm_w = wbbox[2] - wbbox[0]
    draw.text((W - wm_w - 30, H - 60), wm_text, font=wm_font, fill=(255, 255, 255, 200))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    log.info(f"Rendered hook PNG: {output_path}")
    return output_path


def concat_clips(clip_paths: List[Path], output_path: Path) -> Path:
    """Concat multiple mp4 clips with the same codec/resolution into one file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in clip_paths:
            f.write(f"file '{p.absolute()}'\n")
        list_path = Path(f.name)

    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(output_path),
    ], check=True)
    list_path.unlink(missing_ok=True)
    log.info(f"Concatenated {len(clip_paths)} clips -> {output_path.name}")
    return output_path


def normalize(src_mp4: Path, output_path: Path) -> Path:
    """Re-encode an arbitrary input mp4 to 1080x1920 30fps H.264 (IG Reels safe).
    Preserves source audio (re-encoded to AAC 192k). Uses the fill-and-crop pattern
    proven in processor/movie_edit.py — scales up to fully cover 9:16 then crops center."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src_mp4),
        "-vf", vf,
        "-r", "30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    log.info(f"Normalizing {src_mp4.name} -> {output_path.name} ({W}x{H} 30fps)")
    subprocess.run(cmd, check=True)
    return output_path


# Subtitle typography for PIL-rendered PNG overlays (no drawtext/libass needed).
_SUB_FONTSIZE = 46
_SUB_BORDER_W = 5
_SUB_Y_FROM_BOTTOM = 280   # px from bottom of 1920-tall frame (above IG UI zone)
_SUB_MAX_CHARS_PER_LINE = 26


def _parse_srt(srt_text: str) -> List[tuple]:
    """Return [(start_sec, end_sec, text)] cues."""
    cue = re.compile(
        r"\d+\s*\n"
        r"(\d{2}:\d{2}:\d{2})[,.](\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2})[,.](\d{3})\s*\n"
        r"(.+?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )
    out = []
    for m in cue.finditer(srt_text):
        s_hms, s_ms, e_hms, e_ms, text = m.groups()
        out.append((
            _hms_to_sec(s_hms, s_ms),
            _hms_to_sec(e_hms, e_ms),
            text.strip().replace("\n", " ").rstrip("."),
        ))
    return out


def _hms_to_sec(hms: str, ms: str) -> float:
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _render_sub_png(text: str, output_path: Path) -> Path:
    """Render one subtitle line as a transparent PNG the size of the video."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    lines = _wrap_text(text, max_chars=_SUB_MAX_CHARS_PER_LINE)
    font = _find_font(_SUB_FONTSIZE)
    line_h = int(_SUB_FONTSIZE * 1.15)
    total_h = line_h * len(lines)
    y = H - _SUB_Y_FROM_BOTTOM - total_h
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (W - w) // 2
        for dx, dy in [(-_SUB_BORDER_W, 0), (_SUB_BORDER_W, 0),
                       (0, -_SUB_BORDER_W), (0, _SUB_BORDER_W),
                       (-_SUB_BORDER_W, -_SUB_BORDER_W), (_SUB_BORDER_W, _SUB_BORDER_W),
                       (-_SUB_BORDER_W, _SUB_BORDER_W), (_SUB_BORDER_W, -_SUB_BORDER_W)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 230))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def finalize(
    concat_video: Path,
    hook_png: Path,
    voice_path: Optional[Path],
    output_path: Path,
    srt_path: Optional[Path] = None,
) -> Path:
    """Single-pass finalize: concat video + hook PNG overlay (first 2.5s) + subtitle
    PNG overlays (per SRT cue, time-gated) + voice audio mux.
    Uses only ffmpeg's overlay filter (no drawtext/libass needed)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fade_out_start = HOOK_HOLD_SEC - HOOK_FADE_SEC

    has_subs = srt_path and Path(srt_path).exists()
    cues = _parse_srt(Path(srt_path).read_text()) if has_subs else []

    sub_pngs = []
    if cues:
        sub_dir = output_path.parent / f"{output_path.stem}_subs"
        sub_dir.mkdir(parents=True, exist_ok=True)
        for i, (_start, _end, text) in enumerate(cues):
            png = _render_sub_png(text, sub_dir / f"sub_{i:03d}.png")
            sub_pngs.append(png)

    # Filter chain: hook overlay -> each subtitle overlay
    filter_parts = [
        f"[1:v]format=rgba,"
        f"fade=t=in:st=0:d={HOOK_FADE_SEC}:alpha=1,"
        f"fade=t=out:st={fade_out_start}:d={HOOK_FADE_SEC}:alpha=1[hook]",
        f"[0:v][hook]overlay=0:0:enable='between(t,0,{HOOK_HOLD_SEC})'[v0]",
    ]
    # Each subtitle PNG occupies input index (2 + i) — voice mp3 (if any) goes last.
    for i, (start, end, _text) in enumerate(cues):
        sub_idx = 2 + i  # 0=video, 1=hook_png, 2..N+1=sub pngs
        in_label = f"v{i}"
        out_label = f"v{i + 1}"
        filter_parts.append(
            f"[{sub_idx}:v]format=rgba[sub{i}]"
        )
        filter_parts.append(
            f"[{in_label}][sub{i}]overlay=0:0:enable='between(t,{start:.3f},{end:.3f})'[{out_label}]"
        )
    final_label = f"v{len(cues)}"

    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-i", str(concat_video),
           "-i", str(hook_png)]
    for png in sub_pngs:
        cmd += ["-i", str(png)]
    if voice_path:
        cmd += ["-i", str(voice_path)]
        voice_idx = 2 + len(sub_pngs)
    cmd += ["-filter_complex", ";".join(filter_parts),
            "-map", f"[{final_label}]"]
    if voice_path:
        cmd += ["-map", f"{voice_idx}:a"]
    else:
        cmd += ["-map", "0:a?"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path)]

    audio_src = "voice mp3" if voice_path else "source video audio"
    log.info(f"Finalizing -> {output_path.name} (audio: {audio_src}, subtitle cues: {len(cues)})")
    subprocess.run(cmd, check=True)
    return output_path
