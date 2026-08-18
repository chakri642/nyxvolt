import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.dates as mdates

log = logging.getLogger(__name__)

WIDTH_PX = 1080
HEIGHT_PX = 1920
DPI = 100
FPS = 30
DRAW_SECONDS = 22
REVEAL_SECONDS = 4
HOLD_SECONDS = 1
TOTAL_SECONDS = DRAW_SECONDS + REVEAL_SECONDS + HOLD_SECONDS

BG = "#0a0a0f"
FG = "#ffffff"
LINE_COLOR = "#00ff9c"
EVENT_COLOR = "#ff3860"
GAIN_COLOR = "#00ff9c"


def _strip_emoji(s: str) -> str:
    """matplotlib default fonts don't have emoji glyphs — strip to avoid boxes."""
    return re.sub(r"[^\x00-\x7F]+", "", s).strip()


def render(
    portfolio: pd.Series,
    hook: str,
    final_line: str,
    events: List[Dict],
    initial_investment: float,
    output_path: Path,
    audio_path: Optional[Path] = None,
) -> Path:
    """Render a 1080x1920 line-chart animation to mp4.
    If audio_path given, mux it in as the soundtrack via ffmpeg."""
    dates = portfolio.index.to_pydatetime()
    values = portfolio.values.astype(float)
    n = len(values)

    total_frames = TOTAL_SECONDS * FPS
    draw_frames = DRAW_SECONDS * FPS
    reveal_start = draw_frames
    reveal_end = draw_frames + REVEAL_SECONDS * FPS

    date_nums = mdates.date2num(dates)
    parsed_events = []
    for ev in events:
        try:
            ev_date = pd.to_datetime(ev["date"]).to_pydatetime()
            if ev_date < dates[0] or ev_date > dates[-1]:
                continue
            ev_num = mdates.date2num(ev_date)
            idx = int(np.searchsorted(date_nums, ev_num))
            idx = min(max(idx, 0), n - 1)
            frame_reveal = int((idx / n) * draw_frames)
            parsed_events.append({
                "label": _strip_emoji(ev["label"])[:32],
                "x": ev_num,
                "y": values[idx],
                "reveal_frame": frame_reveal,
            })
        except Exception as e:
            log.warning(f"Skipping event {ev}: {e}")

    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI, facecolor=BG)

    # Layout: hook header (top ~18%), chart (middle ~62%), footer counter (bottom ~20%)
    ax_hook = fig.add_axes([0.05, 0.82, 0.90, 0.15])
    ax_chart = fig.add_axes([0.10, 0.22, 0.85, 0.55])
    ax_footer = fig.add_axes([0.05, 0.02, 0.90, 0.18])

    for a in (ax_hook, ax_chart, ax_footer):
        a.set_facecolor(BG)
        for spine in a.spines.values():
            spine.set_visible(False)
        a.set_xticks([])
        a.set_yticks([])

    ax_hook.text(
        0.5, 0.5, _wrap(hook, 28), color=FG, fontsize=28, fontweight="bold",
        ha="center", va="center", transform=ax_hook.transAxes,
    )

    # Chart styling
    ax_chart.set_xlim(date_nums[0], date_nums[-1])
    y_min, y_max = float(values.min()), float(values.max())
    y_range = y_max - y_min
    ax_chart.set_ylim(y_min - y_range * 0.10, y_max + y_range * 0.20)
    ax_chart.grid(True, color="#222233", linewidth=0.5, alpha=0.6)
    ax_chart.tick_params(colors="#666677", labelsize=10)
    ax_chart.spines["bottom"].set_visible(True)
    ax_chart.spines["bottom"].set_color("#333344")
    ax_chart.xaxis.set_major_locator(mdates.YearLocator())
    ax_chart.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    for lbl in ax_chart.get_xticklabels():
        lbl.set_color("#888899")

    (line,) = ax_chart.plot([], [], color=LINE_COLOR, linewidth=3.2, solid_capstyle="round")
    dot = ax_chart.scatter([], [], s=90, color=FG, zorder=5, edgecolors=LINE_COLOR, linewidths=2)

    event_artists = []
    for ev in parsed_events:
        marker = ax_chart.scatter([], [], s=0, color=EVENT_COLOR, zorder=6)
        txt = ax_chart.text(
            ev["x"], ev["y"], "", color=FG, fontsize=13, fontweight="bold",
            ha="center", va="bottom",
            bbox=dict(boxstyle="round,pad=0.4", facecolor=EVENT_COLOR, edgecolor="none", alpha=0.0),
        )
        event_artists.append((ev, marker, txt))

    year_text = ax_footer.text(
        0.5, 0.75, "", color="#888899", fontsize=22, fontweight="bold",
        ha="center", va="center", transform=ax_footer.transAxes,
    )
    value_text = ax_footer.text(
        0.5, 0.30, "", color=GAIN_COLOR, fontsize=64, fontweight="bold",
        ha="center", va="center", transform=ax_footer.transAxes,
    )
    reveal_text = fig.text(
        0.5, 0.50, "", color=FG, fontsize=42, fontweight="bold",
        ha="center", va="center", visible=False,
    )

    def _update(frame: int):
        if frame < draw_frames:
            progress = frame / draw_frames
            idx = max(1, int(progress * n))
            line.set_data(date_nums[:idx], values[:idx])
            dot.set_offsets([[date_nums[idx - 1], values[idx - 1]]])
            current_val = values[idx - 1]
            current_date = dates[idx - 1]
            year_text.set_text(current_date.strftime("%b %Y"))
            value_text.set_text(f"${current_val:,.0f}")
            value_text.set_color(GAIN_COLOR if current_val >= initial_investment else EVENT_COLOR)

            for ev, marker, txt in event_artists:
                if frame >= ev["reveal_frame"]:
                    frames_since = frame - ev["reveal_frame"]
                    alpha = min(1.0, frames_since / 8.0)
                    marker.set_offsets([[ev["x"], ev["y"]]])
                    marker.set_sizes([120 + max(0, 30 - frames_since) * 6])
                    marker.set_alpha(alpha)
                    txt.set_text(ev["label"])
                    txt.set_alpha(alpha)
                    txt.get_bbox_patch().set_alpha(alpha * 0.85)
        else:
            # Draw complete — hold + reveal
            line.set_data(date_nums, values)
            dot.set_offsets([[date_nums[-1], values[-1]]])
            year_text.set_text(dates[-1].strftime("%b %Y"))
            value_text.set_text(f"${values[-1]:,.0f}")
            for ev, marker, txt in event_artists:
                marker.set_offsets([[ev["x"], ev["y"]]])
                marker.set_sizes([120])
                marker.set_alpha(1.0)
                txt.set_text(ev["label"])
                txt.set_alpha(1.0)
                txt.get_bbox_patch().set_alpha(0.85)

            if reveal_start <= frame < reveal_end:
                fade = min(1.0, (frame - reveal_start) / (FPS * 0.5))
                reveal_text.set_text(_strip_emoji(final_line))
                reveal_text.set_visible(True)
                reveal_text.set_alpha(fade)

        return [line, dot, year_text, value_text, reveal_text] + [m for _, m, _ in event_artists] + [t for _, _, t in event_artists]

    log.info(f"Rendering {total_frames} frames @ {FPS}fps ({TOTAL_SECONDS}s)...")
    anim = animation.FuncAnimation(fig, _update, frames=total_frames, interval=1000 / FPS, blit=False)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if audio_path is None:
        writer = animation.FFMpegWriter(
            fps=FPS, codec="libx264",
            extra_args=["-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "23"],
        )
        anim.save(str(output_path), writer=writer, dpi=DPI)
    else:
        # Render silent video to temp, then mux audio
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            silent = Path(tmp.name)
        writer = animation.FFMpegWriter(
            fps=FPS, codec="libx264",
            extra_args=["-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "23"],
        )
        anim.save(str(silent), writer=writer, dpi=DPI)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(silent), "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path),
        ], check=True)
        silent.unlink(missing_ok=True)

    plt.close(fig)
    log.info(f"Rendered: {output_path}")
    return output_path


def _wrap(text: str, max_chars: int) -> str:
    """Simple word-wrap into multiple lines so the hook fits inside the header box."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)
