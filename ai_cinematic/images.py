"""Image generation via Google AI Studio (Gemini 2.5 Flash Image, free tier).

Setup (one-time):
1. https://aistudio.google.com/apikey  ->  Create API key (Google login, no card)
2. Add to .env:  GEMINI_API_KEY=AIzaSy...

Free tier: 10 requests/min, ~500/day for gemini-2.5-flash-image. 8 images per reel
= ~1 min per reel of fetches. ~60 reels/day headroom.

Emergency fallback: set HF_FLUX_FALLBACK_TO_POLLINATIONS=1 in .env to route through
Pollinations flux-realism instead (lower quality but no key needed).
"""
import io
import logging
import os
import random
import time
from pathlib import Path
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-image"  # "lite" tier is more likely to have free quota
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash-image"  # try older stable as backup if lite is unavailable

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
POLLINATIONS_WIDTH = 1440
POLLINATIONS_HEIGHT = 2560

TIMEOUT = 120
RETRIES = 4
BACKOFF_SEC = 10
MIN_BYTES = 5000

_gemini_client = None


class _RetryableError(Exception):
    def __init__(self, msg: str, wait_sec: float = BACKOFF_SEC):
        super().__init__(msg)
        self.wait_sec = wait_sec


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Add it to .env — get key at https://aistudio.google.com/apikey"
            )
        from google import genai
        _gemini_client = genai.Client(api_key=key)
    return _gemini_client


def _fetch_gemini(prompt: str, seed: int, model: str = GEMINI_MODEL) -> bytes:
    """Google AI Studio Gemini image gen. Returns image bytes.
    On 404 (model unavailable on account), auto-swaps to GEMINI_FALLBACK_MODEL once."""
    from google.genai import types
    client = _get_gemini_client()
    prompt_with_format = prompt + "\n\nRender as vertical 9:16 aspect ratio, cinematic quality."

    def _call(m):
        return client.models.generate_content(
            model=m,
            contents=prompt_with_format,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

    try:
        r = _call(model)
    except Exception as e:
        msg = str(e)
        if "404" in msg or "NOT_FOUND" in msg:
            log.warning(f"Gemini model {model} 404 — trying {GEMINI_FALLBACK_MODEL}")
            try:
                r = _call(GEMINI_FALLBACK_MODEL)
            except Exception as e2:
                msg2 = str(e2)
                if "429" in msg2 or "RESOURCE_EXHAUSTED" in msg2:
                    raise _RetryableError(f"Gemini 429 rate-limited ({GEMINI_FALLBACK_MODEL})", wait_sec=15)
                raise RuntimeError(f"Both Gemini models failed: {model} 404, {GEMINI_FALLBACK_MODEL}: {msg2[:200]}")
        elif "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            raise _RetryableError(f"Gemini 429 rate-limited ({model})", wait_sec=15)
        elif "500" in msg or "503" in msg or "INTERNAL" in msg or "UNAVAILABLE" in msg:
            raise _RetryableError(f"Gemini server error: {msg[:200]}", wait_sec=10)
        else:
            raise RuntimeError(f"Gemini error: {msg[:300]}")

    if not r.candidates:
        raise RuntimeError(f"Gemini returned no candidates: {r}")
    for part in r.candidates[0].content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            if len(inline.data) < MIN_BYTES:
                raise ValueError(f"Gemini returned only {len(inline.data)} bytes")
            return inline.data
    raise RuntimeError(f"Gemini response had no image data. Text output: {r.text[:200] if hasattr(r, 'text') else '<none>'}")


def _fetch_pollinations(prompt: str, seed: int) -> bytes:
    """Fallback path — Pollinations flux-realism, no auth needed."""
    url = POLLINATIONS_URL.format(prompt=quote(prompt))
    params = {
        "width": POLLINATIONS_WIDTH,
        "height": POLLINATIONS_HEIGHT,
        "nologo": "true",
        "enhance": "true",
        "model": "flux-realism",
        "seed": seed,
    }
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    if len(r.content) < MIN_BYTES:
        raise ValueError(f"Pollinations returned only {len(r.content)} bytes")
    return r.content


def fetch(prompt: str, output_path: Path, seed: int = None) -> Path:
    """Fetch one image. Gemini primary; retries on rate-limit / server errors."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seed = seed if seed is not None else random.randint(1, 999_999_999)
    use_fallback = os.environ.get("HF_FLUX_FALLBACK_TO_POLLINATIONS") == "1"

    for attempt in range(1, RETRIES + 1):
        provider = "pollinations" if use_fallback else "gemini"
        try:
            log.info(f"Fetching image via {provider} (attempt {attempt}, seed={seed}): {prompt[:90]}...")
            if use_fallback:
                data = _fetch_pollinations(prompt, seed)
            else:
                data = _fetch_gemini(prompt, seed)
            output_path.write_bytes(data)
            log.info(f"Saved image ({len(data):,} bytes) via {provider}: {output_path.name}")
            return output_path
        except _RetryableError as e:
            log.warning(f"Attempt {attempt} retryable: {e}")
            if attempt < RETRIES:
                time.sleep(e.wait_sec)
                seed = random.randint(1, 999_999_999)
            else:
                raise RuntimeError(f"{provider} failed after {RETRIES} attempts: {e}")
        except (requests.RequestException, ValueError) as e:
            log.warning(f"Attempt {attempt} failed: {e}")
            if attempt < RETRIES:
                time.sleep(BACKOFF_SEC * attempt)
                seed = random.randint(1, 999_999_999)
            else:
                raise RuntimeError(f"{provider} failed after {RETRIES} attempts: {e}")
    raise RuntimeError("unreachable")


def fetch_all(prompts: list, output_dir: Path, prefix: str = "scene") -> list:
    """Fetch a list of prompts to sequentially numbered files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, prompt in enumerate(prompts):
        out = output_dir / f"{prefix}_{i + 1}.jpg"
        fetch(prompt, out)
        paths.append(out)
    return paths
