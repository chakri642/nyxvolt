import os
import requests
from pathlib import Path
from config import CLIPS_PROCESSED


def generate(text: str, output_name: str = "voiceover.mp3") -> Path:
    voice_id = os.environ["ELEVENLABS_VOICE_ID"]
    api_key = os.environ["ELEVENLABS_API_KEY"]
    output = CLIPS_PROCESSED / output_name

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.8,
                "style": 0.6,
                "use_speaker_boost": True,
            },
        },
        timeout=30,
    )
    resp.raise_for_status()
    output.write_bytes(resp.content)
    return output
