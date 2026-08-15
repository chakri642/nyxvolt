import subprocess
import tempfile
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import CLIPS_PROCESSED, OUTPUT_WIDTH, OUTPUT_HEIGHT

SPEED = 0.90
SATURATION = 1.15
CONTRAST = 1.20
GAMMA = 0.95

BRAND_HANDLE = "@nyxvolt"

# Font paths — macOS system paths first, then Linux (Colab).
# Critical: PIL's ImageFont.load_default() is a fixed 8px bitmap and IGNORES the
# size argument, so if no truetype font is found, text renders unreadably small.
BOLD_FONTS = [
    ("/System/Library/Fonts/SFNSRounded.ttf", 0),
    ("/System/Library/Fonts/SFCompactRounded.ttf", 0),
    ("/System/Library/Fonts/Avenir Next.ttc", 1),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 0),
    ("/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf", 0),
    ("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf", 0),
    (str(Path(__file__).parent.parent / "assets" / "font.ttf"), 0),
]

# Regular-weight sans for hook (softer TikTok/meme look — see Image #7).
REGULAR_FONTS = [
    ("/System/Library/Fonts/SFNS.ttf", 0),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", 0),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 0),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", 0),
    ("/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf", 0),
    ("/usr/share/fonts/truetype/freefont/FreeSans.ttf", 0),
    (str(Path(__file__).parent.parent / "assets" / "font.ttf"), 0),
]


def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for path, index in (BOLD_FONTS if bold else REGULAR_FONTS):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=index)
            except Exception:
                continue
    print(f"  WARNING: no truetype font found — text will render at 8px!")
    return ImageFont.load_default()


def _make_text_png(text: str, font_size: int, out_path: Path,
                   canvas_w: int, canvas_h: int,
                   bg_alpha: int = 0, stroke_width: int = 0,
                   bold: bool = True):
    """Render text into a PNG. Supports:
    - Semi-transparent black background bar (bg_alpha 0=transparent, 255=solid)
    - Auto text wrap (breaks long lines to fit width)
    - Font auto-shrink if still overflowing after wrap
    - Optional stroke outline (0 = no stroke)
    - Regular vs bold weight."""
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, bg_alpha))
    draw = ImageDraw.Draw(img)

    max_text_w = canvas_w - 60
    size = font_size

    def _wrap(size):
        font = _load_font(size, bold=bold)
        # Estimate char width from a sample, use it to guess a reasonable wrap width
        avg_char = draw.textbbox((0, 0), "M", font=font)[2] * 0.55
        max_chars = max(6, int(max_text_w / max(avg_char, 1)))
        lines = textwrap.wrap(text, width=max_chars, break_long_words=False) or [text]
        # Check widest line fits
        widest = max(draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)[2] for line in lines)
        return font, lines, widest

    while size > 24:
        font, lines, widest = _wrap(size)
        if widest <= max_text_w:
            break
        size -= 4

    font, lines, _ = _wrap(size)
    line_h = draw.textbbox((0, 0), "Mg", font=font, stroke_width=stroke_width)[3]
    total_h = line_h * len(lines) + (len(lines) - 1) * 8   # 8px line spacing
    y = (canvas_h - total_h) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
        x = (canvas_w - (bbox[2] - bbox[0])) // 2 - bbox[0]
        draw.text(
            (x, y), line, font=font,
            fill=(255, 255, 255, 255),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 235) if stroke_width else None,
        )
        y += line_h + 8

    img.save(out_path)


# Back-compat alias so existing call sites keep working.
_make_outlined_text_png = _make_text_png


def process(video: Path, hook_text: str = None) -> Path:
    """Cinematic movie-edit: slow-mo, color grade, blur bg, watermark crop,
    persistent hook overlay + @nyxvolt brand mark."""
    output = CLIPS_PROCESSED / f"{video.stem}_movieedit.mp4"
    w, h = OUTPUT_WIDTH, OUTPUT_HEIGHT

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # Prep text overlays as transparent PNGs
        hook_png = tmp_dir / "hook.png"
        wm_png = tmp_dir / "wm.png"

        # Watermark: small corner mark — same regular font as hook, smaller size
        wm_canvas_w, wm_canvas_h = 400, 75
        _make_text_png(
            BRAND_HANDLE, font_size=38, out_path=wm_png,
            canvas_w=wm_canvas_w, canvas_h=wm_canvas_h,
            bg_alpha=0, stroke_width=3, bold=False,
        )

        # Hook: transparent bg, regular-weight sans, black stroke for readability
        hook_layer_present = bool(hook_text)
        hook_canvas_w = w
        hook_canvas_h = 280
        if hook_layer_present:
            _make_text_png(
                hook_text, font_size=72, out_path=hook_png,
                canvas_w=hook_canvas_w, canvas_h=hook_canvas_h,
                bg_alpha=0, stroke_width=4, bold=False,
            )

        # Positions
        # Watermark: bottom-right corner
        wm_x = w - wm_canvas_w - 40
        wm_y = h - wm_canvas_h - 120
        # Hook: full-width bar flush to top with a small inset
        hook_x = 0
        hook_y = 100

        # Crop 9% off the bottom to remove any source-creator watermark,
        # then scale-fill 9:16 (center-crop overflow). No blurred mirror bg.
        filter_chain = (
            f"[0:v]setpts=PTS/{SPEED},"
            f"eq=saturation={SATURATION}:contrast={CONTRAST}:gamma={GAMMA},"
            f"crop=iw:ih*0.91:0:0,"
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}[v0];"
            f"[v0][1:v]overlay={wm_x}:{wm_y}[v1]"
        )

        if hook_layer_present:
            filter_chain += f";[v1][2:v]overlay={hook_x}:{hook_y}[v]"
            v_map = "[v]"
        else:
            v_map = "[v1]"

        # Slow the audio to match 0.9x video slow-mo
        filter_chain += f";[0:a]atempo={SPEED}[a]"

        cmd = ["ffmpeg", "-y", "-threads", "0", "-i", str(video), "-i", str(wm_png)]
        if hook_layer_present:
            cmd += ["-i", str(hook_png)]
        cmd += [
            "-filter_complex", filter_chain,
            "-map", v_map,
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output),
        ]

        print(f"  ffmpeg movie-edit (hook='{hook_text or 'none'}')...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg movie edit failed:\n{result.stderr[-2000:]}")

    return output
