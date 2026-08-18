import asyncio
import logging
import re
from pathlib import Path
from typing import Optional, Tuple

import edge_tts

log = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"
DEFAULT_RATE = "+15%"

HOOK_SKIP_SEC = 2.5  # subtitles for lines that end before this are skipped (hook overlay handles it)


def synthesize(
    text: str,
    output_mp3: Path,
    output_srt: Optional[Path] = None,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
) -> Tuple[Path, Optional[Path]]:
    """Generate narration mp3, optionally also generate SRT subtitles.
    Uses edge-tts SentenceBoundary events (voices no longer emit word-level).
    Returns (mp3_path, srt_path or None)."""
    output_mp3 = Path(output_mp3)
    output_mp3.parent.mkdir(parents=True, exist_ok=True)

    log.info(f"Synthesizing narration ({len(text)} chars, voice={voice}, srt={'yes' if output_srt else 'no'})")

    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        submaker = edge_tts.SubMaker() if output_srt else None
        with open(output_mp3, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif submaker and chunk["type"] in ("SentenceBoundary", "WordBoundary"):
                    try:
                        submaker.feed(chunk)
                    except ValueError:
                        pass  # mixed boundary types, ignore extras
        if submaker:
            srt = _postprocess_srt(submaker.get_srt(), skip_before_sec=HOOK_SKIP_SEC)
            Path(output_srt).write_text(srt)

    asyncio.run(_run())
    log.info(f"Narration saved: {output_mp3}" + (f" + SRT: {output_srt}" if output_srt else ""))
    return output_mp3, (Path(output_srt) if output_srt else None)


def _postprocess_srt(srt: str, skip_before_sec: float) -> str:
    """Drop cues that end before skip_before_sec (hook overlay covers that window).
    Also renumber cues to stay sequential."""
    if skip_before_sec <= 0:
        return srt

    cue_pattern = re.compile(
        r"(\d+)\s*\n"
        r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n"
        r"(.+?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )

    kept = []
    for m in cue_pattern.finditer(srt):
        _idx, start, end, body = m.groups()
        end_sec = _srt_to_sec(end)
        if end_sec <= skip_before_sec:
            continue
        kept.append((start, end, body.strip()))

    out_lines = []
    for i, (start, end, body) in enumerate(kept, 1):
        out_lines.append(str(i))
        out_lines.append(f"{start} --> {end}")
        out_lines.append(body)
        out_lines.append("")
    return "\n".join(out_lines).strip() + "\n"


def _srt_to_sec(ts: str) -> float:
    ts = ts.replace(",", ".")
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)
