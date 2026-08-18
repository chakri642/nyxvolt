import json
import logging
import os
import random
import re
from datetime import datetime
from pathlib import Path
import anthropic

log = logging.getLogger(__name__)

HISTORY_PATH = Path(__file__).parent / "history.json"
NUM_IMAGES = 8
CLIP_LEN_SEC = 5.0  # each image -> 5s Ken Burns clip; 8 * 5 = 40s reel
MOTIONS = ["zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]

_client = None

SUB_NICHES = [
    ("extreme_scenario", "What if you did [dangerous/impossible physical thing]? e.g. 'jumped from 100th floor', 'swam to bottom of Mariana Trench'"),
    ("removal", "What if [something taken for granted] didn't exist? e.g. 'movies never existed', 'gravity turned off for 10 seconds'"),
    ("time_transposition", "What if [historical figure] was born today? e.g. 'Newton in 2026', 'Einstein with the internet'"),
    ("disaster_survival", "What if [catastrophic thing] happened right now? e.g. 'both plane engines cut out', 'the sun disappeared for one hour'"),
    ("amplification", "What if [something familiar] was [10x/100x] different? e.g. 'moon was 10x closer', 'humans were 3 meters tall'"),
]

SYSTEM_PROMPT = """You write concepts for a faceless AI-cinematic Instagram Reel channel called @nyxvolt.

Each reel is 8 photorealistic AI-generated STILL IMAGES stitched with Ken Burns camera motion, over an edge-tts voice narration and a bold hook text overlay + word-timed subtitles. Total ~40 seconds.

**The FIRST 3 SECONDS asks the "What If" QUESTION.** The rest of the reel ANSWERS it in cinematic detail. This is Vsauce / Kurzgesagt / Veritasium format.

**Critical:** subject in each image must be CENTER-COMPOSED. Our pipeline crops the sides (Cloudflare returns square images, we crop to 9:16). Anything on the far left/right edges gets cut. Frame the subject dead center.

You MUST return valid JSON with this exact shape:
{
  "concept": "One-sentence description of the 'what if' scenario",
  "sub_niche": "one of: extreme_scenario, removal, time_transposition, disaster_survival, amplification",
  "hook": "6-10 word hook shown as bold text overlay on first 2.5 seconds. Start with 'What if' or a punchier variant.",
  "caption": "2-line IG caption. Line 1: punchy statement that plants curiosity. Line 2: an easy-to-answer question that begs a comment. Max 2 tasteful emojis. NO hashtags. NO em/en dashes.",
  "hashtags": ["4-6 niche-specific tags, lowercase, no # prefix, no spaces. NO 'viral' 'fyp' 'trending'."],
  "narration": {
    "hook_line": "The QUESTION. ONE sentence, 10-14 words. Spoken loud in the FIRST 3 seconds while image 1 is on screen. Example: 'What if a second sun appeared in our solar system tomorrow morning?'",
    "body": "The ANSWER. 12-16 SHORT SENTENCES, each 5-9 words. This is CRITICAL: each sentence becomes ONE subtitle line, so long sentences look bad. Vsauce/Kurzgesagt tone. Clear narrative arc: first effects -> second-order effects -> climax. Example: 'Within seconds, temperatures would spike. Oceans would begin to boil. Forests would ignite worldwide. Every shadow would vanish. Gravity itself would warp. Earth's orbit would slowly bend. The atmosphere would strip away. Life would end in days.'",
    "payoff": "The CLOSING. ONE OR TWO short sentences (10-15 words total). Ends with a thought-provoking question or haunting statement that begs a comment. Example: 'The end came not from fire, but from the silence.'"
  },
  "image_prompts": [
    "8 detailed Flux-friendly image prompts, one per scene. Each is a photorealistic cinematic still.",
    "Image 1: the QUESTION shot — visually poses the 'what if' scenario dramatically",
    "Images 2-7: the ANSWER — escalating consequences shown across 6 beats matching the narration body",
    "Image 8: the PAYOFF — haunting final image that lingers",
    "SUBJECTS MUST BE CENTER-COMPOSED (sides get cropped in post).",
    "5 more entries — exactly 8 total.",
    "",
    ""
  ],
  "motions": [
    "8 Ken Burns motion types, one per image. Choose from: zoom_in, zoom_out, pan_left, pan_right, pan_up, pan_down.",
    "NEVER repeat the same motion in adjacent scenes.",
    "Pairing guide: wide/atmospheric = zoom_in (draws viewer in), close-up = zoom_out (reveal context), aerial = pan_left/right.",
    "5 more entries — exactly 8 total.",
    "",
    "",
    "",
    ""
  ]
}

RULES FOR EACH `image_prompts` ENTRY:

Write a comma-separated tag list (Flux/SDXL best practice), 30-60 words, ending with the trailer literally: `centered composition, no text, no letters, no logos, no watermark`.

Template order:
[subject and action, CENTERED in frame], [environment/setting], [lighting — motivated, direction, color], [camera angle/lens — anamorphic 2x, shallow depth of field, low angle / wide / close-up / drone / etc.], cinematic film still, photorealistic, hyperdetailed, shot on Arri Alexa, [color grade — pick ONE per reel and use across all 8: teal-orange OR desaturated cool OR warm nostalgic OR monochrome with one accent color], centered composition, no text, no letters, no logos, no watermark

Composition variety across the 8 images (do NOT repeat same shot type; subject always centered):
- Two wides / establishing / drone views (subject in center third)
- Two extreme close-ups (object, hand, eye, texture — center-framed)
- One POV first-person perspective (centered horizon)
- One overhead / top-down (subject center of frame)
- One low-angle hero shot (subject dead center)
- One environmental medium shot (subject centered)

Continuity rule: same color grade across all 8 images (pick ONE grade in image 1 and repeat it). Same lighting time-of-day. Feels like one story escalating.

Concept rules:
- Pick ONE sub_niche from: __SUB_NICHES__
- Concept must be visually cinematic and require no dialogue.
- The FIRST image must ALREADY SHOW the impossible/dramatic thing — no build-up.
- AVOID: sports moments, comedy skits, fights with named characters, copyrighted franchises.
- Real historical figures OK (Newton, Einstein, Da Vinci).
- NEVER repeat concepts from the DO-NOT-REPEAT list.
- Output ONLY the JSON. No markdown, no code fences, no commentary."""


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text())
    except json.JSONDecodeError:
        log.warning("history.json corrupt, starting fresh")
        return []


def _save_to_history(entry: dict) -> None:
    hist = _load_history()
    hist.append(entry)
    HISTORY_PATH.write_text(json.dumps(hist, indent=2))


def _format_dont_repeat(hist: list) -> str:
    if not hist:
        return "(no prior concepts — you have a blank slate)"
    return "\n".join(
        f"- [{e.get('sub_niche', '?')}] {e['concept']} | hook: \"{e['hook']}\""
        for e in hist[-50:]
    )


def _sub_niche_balance_hint(hist: list) -> str:
    if len(hist) < 3:
        return "(mix freely across sub_niches)"
    recent = [e.get("sub_niche") for e in hist[-5:]]
    counts = {sn: recent.count(sn) for sn, _ in SUB_NICHES}
    overused = [sn for sn, c in counts.items() if c >= 2]
    if overused:
        return f"(you've used {overused} recently — pick a DIFFERENT sub_niche this time)"
    return "(mix freely across sub_niches)"


def _extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Claude usually returns prose instead of JSON when it declines a topic (safety refusal)
        # or when a system-prompt rule was violated. Surface what Claude actually said.
        preview = text[:400].replace("\n", " ")
        raise RuntimeError(
            f"Claude did not return valid JSON. It likely refused this topic (safety policy) "
            f"or the prompt confused it. Claude said:\n\n  {preview}\n\n"
            f"Try a different topic — safer/less explicit topics work reliably."
        )


def _validate_motions(motions: list) -> list:
    """Ensure 6 motions, all valid, no adjacent duplicates. Fix violations."""
    if len(motions) != NUM_IMAGES:
        raise ValueError(f"Expected {NUM_IMAGES} motions, got {len(motions)}")
    cleaned = []
    for i, m in enumerate(motions):
        if m not in MOTIONS:
            log.warning(f"Motion {i} '{m}' invalid, defaulting to zoom_in")
            m = "zoom_in"
        if cleaned and cleaned[-1] == m:
            # Swap to something different
            alt = [x for x in MOTIONS if x != m][i % (len(MOTIONS) - 1)]
            log.info(f"Motion {i} same as prev, swapping {m} -> {alt}")
            m = alt
        cleaned.append(m)
    return cleaned


def pick_concept(user_topic: str = None) -> dict:
    """Ask Claude for a fresh 'What If' concept. If user_topic is given, build the concept around that exact topic instead of picking freely."""
    hist = _load_history()
    dont_repeat = _format_dont_repeat(hist)
    balance = _sub_niche_balance_hint(hist)
    sub_niches_str = ", ".join(f"{name} ({desc})" for name, desc in SUB_NICHES)

    if user_topic:
        log.info(f"Building concept around user topic: {user_topic!r}")
        topic_directive = (
            f"USER-SPECIFIED TOPIC (build the concept around this exact 'what if' idea):\n"
            f"    \"{user_topic}\"\n"
            f"Normalize awkward phrasing to good English if needed (e.g. 'bulb invention' -> 'the light bulb was never invented'), "
            f"but keep the core idea. Choose the sub_niche that best fits. Ignore the anti-repeat balance hint "
            f"(the user wants this specific topic).\n\n"
        )
    else:
        log.info(f"Picking concept (history has {len(hist)} prior entries)")
        topic_directive = ""

    client = _get_client()
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3500,
        system=SYSTEM_PROMPT.replace("__SUB_NICHES__", sub_niches_str),
        messages=[{
            "role": "user",
            "content": (
                f"{topic_directive}"
                f"DO-NOT-REPEAT list (past reels — pick something clearly different):\n{dont_repeat}\n\n"
                f"Sub_niche balance hint: {balance}\n"
                f"Random seed for variety: {random.randint(1, 99999)}\n\n"
                f"Return the JSON with exactly {NUM_IMAGES} image_prompts and {NUM_IMAGES} motions. Narration body must be 12-16 SHORT sentences (5-9 words each) that ANSWER the question."
            ),
        }],
    )
    concept = _extract_json(msg.content[0].text)

    required = {"concept", "sub_niche", "hook", "caption", "hashtags", "narration", "image_prompts", "motions"}
    missing = required - set(concept.keys())
    if missing:
        raise ValueError(f"Claude output missing fields: {missing}")
    if len(concept["image_prompts"]) != NUM_IMAGES:
        raise ValueError(f"Expected {NUM_IMAGES} image_prompts, got {len(concept['image_prompts'])}")
    narration_required = {"hook_line", "body", "payoff"}
    if not narration_required.issubset(concept["narration"]):
        raise ValueError(f"narration missing fields: {narration_required - set(concept['narration'])}")

    concept["motions"] = _validate_motions(concept["motions"])

    entry = {
        "picked_at": datetime.utcnow().isoformat() + "Z",
        "concept": concept["concept"],
        "sub_niche": concept["sub_niche"],
        "hook": concept["hook"],
    }
    _save_to_history(entry)
    log.info(f"Picked [{concept['sub_niche']}]: {concept['concept']}")
    log.info(f"Hook: \"{concept['hook']}\"")
    return concept
