"""Preview an edge-tts voice with a sample line, then open the mp3.

Usage:
    python3 try_voice.py                          # default voice
    python3 try_voice.py en-US-DavisNeural
    python3 try_voice.py en-US-BrianNeural +20%   # voice + rate
"""
import asyncio
import subprocess
import sys
from pathlib import Path
import edge_tts

SAMPLE = (
    "If you invested one hundred dollars in Bitcoin in twenty fifteen, "
    "here's what happened. By twenty twenty five, that hundred dollars "
    "would be worth almost thirty thousand."
)

voice = sys.argv[1] if len(sys.argv) > 1 else "en-US-GuyNeural"
rate = sys.argv[2] if len(sys.argv) > 2 else "+15%"
out = Path(f"/tmp/voice_{voice}.mp3")

async def main():
    tts = edge_tts.Communicate(SAMPLE, voice, rate=rate)
    await tts.save(str(out))

asyncio.run(main())
print(f"Saved: {out}")
subprocess.run(["open", str(out)])
