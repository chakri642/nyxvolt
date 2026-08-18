import asyncio
import logging
from pathlib import Path
import edge_tts

log = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"
DEFAULT_RATE = "+15%"


def synthesize(text: str, output_path: Path, voice: str = DEFAULT_VOICE, rate: str = DEFAULT_RATE) -> Path:
    """Generate an mp3 narration of `text` using edge-tts. Returns path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run():
        tts = edge_tts.Communicate(text, voice, rate=rate)
        await tts.save(str(output_path))

    log.info(f"Synthesizing voiceover ({len(text)} chars, voice={voice})")
    asyncio.run(_run())
    log.info(f"Voiceover saved: {output_path}")
    return output_path
