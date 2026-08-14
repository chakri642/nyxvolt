import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from config import CLIPS_PROCESSED, OUTPUT_WIDTH, OUTPUT_HEIGHT

SPEED = 0.90
SATURATION = 1.15
CONTRAST = 1.20
GAMMA = 0.95

BRAND_HANDLE = "@nyxvolt"

# Poppins-style rounded fonts on macOS (SF Pro Rounded is closest to Poppins)
BOLD_FONTS = [
    ("/System/Library/Fonts/SFNSRounded.ttf", 0),      # SF Pro Rounded (Poppins-like)
    ("/System/Library/Fonts/SFCompactRounded.ttf", 0),
    ("/System/Library/Fonts/Avenir Next.ttc", 1),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0),
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path, index in BOLD_FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size, index=index)
            except Exception:
                continue
    return ImageFont.load_default()


def _make_outlined_text_png(text: str, font_size: int, out_path: Path,
                            canvas_w: int, canvas_h: int,
                            stroke_width: int = 4):
    """White text with black outline — clean Poppins-style, no background pill."""
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _load_font(font_size)

    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (canvas_w - text_w) // 2 - bbox[0]
    y = (canvas_h - text_h) // 2 - bbox[1]

    draw.text(
        (x, y), text, font=font,
        fill=(255, 255, 255, 255),
        stroke_width=stroke_width, stroke_fill=(0, 0, 0, 235),
    )
    img.save(out_path)


def process(video: Path, hook_text: str = None) -> Path:
    """Cinematic movie-edit: slow-mo, color grade, blur bg, watermark crop,
    persistent hook overlay + @nyxvolt brand mark."""
    output = CLIPS_PROCESSED / f"{video.stem}_movieedit.mp4"
    w, h = OUTPUT_WIDTH, OUTPUT_HEIGHT

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # Prep text overlays as transparent PNGs with pill backgrounds
        hook_png = tmp_dir / "hook.png"
        wm_png = tmp_dir / "wm.png"

        # Watermark: small outlined text, bottom-right
        _make_outlined_text_png(
            BRAND_HANDLE, font_size=36, out_path=wm_png,
            canvas_w=320, canvas_h=80, stroke_width=2,
        )

        # Hook: bold outlined text, top-center, sentence case (Poppins-style)
        hook_layer_present = bool(hook_text)
        if hook_layer_present:
            _make_outlined_text_png(
                hook_text, font_size=64, out_path=hook_png,
                canvas_w=w - 60, canvas_h=180, stroke_width=5,
            )

        # Build filter chain
        # 1. slow-mo + grade, split into bg/fg
        # 2. bg: fill + blur + dim
        # 3. fg: strip bottom 9% (remove watermarks), fit to frame
        # 4. compose bg+fg → v_base
        # 5. overlay watermark bottom-right
        # 6. overlay hook top-center (if present)
        wm_x = w - 320 - 20    # right edge, small margin
        wm_y = h - 80 - 40     # bottom edge
        hook_x = 30            # centered horizontally, canvas is w-60
        hook_y = 120           # 120px from top

        filter_chain = (
            f"[0:v]setpts=PTS/{SPEED},"
            f"eq=saturation={SATURATION}:contrast={CONTRAST}:gamma={GAMMA},"
            f"split=2[bg_src][fg_src];"
            f"[bg_src]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},boxblur=25:5,eq=brightness=-0.30[bg];"
            f"[fg_src]crop=iw:ih*0.91:0:0,"
            f"scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v0];"
            f"[v0][1:v]overlay={wm_x}:{wm_y}[v1]"
        )

        if hook_layer_present:
            filter_chain += f";[v1][2:v]overlay={hook_x}:{hook_y}[v]"
            v_map = "[v]"
        else:
            v_map = "[v1]"

        # Slow the audio to match 0.9x video slow-mo
        filter_chain += f";[0:a]atempo={SPEED}[a]"

        cmd = ["ffmpeg", "-y", "-i", str(video), "-i", str(wm_png)]
        if hook_layer_present:
            cmd += ["-i", str(hook_png)]
        cmd += [
            "-filter_complex", filter_chain,
            "-map", v_map,
            "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output),
        ]

        print(f"  ffmpeg movie-edit (hook='{hook_text or 'none'}')...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg movie edit failed:\n{result.stderr[-2000:]}")

    return output
