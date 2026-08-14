import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import CLIPS_PROCESSED, OUTPUT_WIDTH, OUTPUT_HEIGHT


def overlay(video: Path, hook_text: str) -> Path:
    output = CLIPS_PROCESSED / f"{video.stem}_overlaid.mp4"
    text_png = Path(tempfile.mktemp(suffix=".png"))

    try:
        _create_text_image(hook_text, text_png)
        _burn_overlay(video, text_png, output)
    finally:
        text_png.unlink(missing_ok=True)

    return output


def _create_text_image(text: str, out_path: Path):
    img = Image.new("RGBA", (OUTPUT_WIDTH, OUTPUT_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = 80
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Impact.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Impact.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    # Word-wrap at ~16 chars per line
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) > 16 and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    line_height = font_size + 10
    total_text_height = len(lines) * line_height
    margin_y = OUTPUT_HEIGHT - total_text_height - int(OUTPUT_HEIGHT * 0.06)

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (OUTPUT_WIDTH - w) // 2 - bbox[0]
        y = margin_y + i * line_height

        # Black stroke
        for dx in [-3, -2, 0, 2, 3]:
            for dy in [-3, -2, 0, 2, 3]:
                draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, 255))
        # White text
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    img.save(str(out_path), "PNG")


def _burn_overlay(video: Path, text_png: Path, output: Path):
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(text_png),
        "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
        "-map", "[v]",
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg overlay failed:\n{result.stderr[-2000:]}")
