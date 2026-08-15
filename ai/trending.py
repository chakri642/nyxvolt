import json
import os
import random
import re
import anthropic

_client = None

CATEGORIES = [
    "MrBeast challenges and giveaways",
    "iShowSpeed streaming moments",
    "NBA basketball highlights",
    "football/soccer highlights (Messi, Ronaldo, Haaland)",
    "movie clips and cinematic edits",
    "anime scene edits (Naruto, One Piece, Jujutsu Kaisen, Attack on Titan)",
    "Marvel/superhero movie moments",
    "viral street interviews and reactions",
    "F1 racing highlights",
    "UFC/MMA knockout moments",
]

# Fallback if Claude fails to return valid JSON
BRAINROT_FALLBACK = [
    "subwaysurfers",
    "subwaysurfersgameplay",
    "minecraftparkourclips",
    "geometrydash.clips",
    "hydraulicpresschannel",
]


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def _extract_json(raw: str) -> dict:
    """Pull the first {...} block out of a Claude response, robust to markdown/prose."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in response: {raw[:200]}")
    return json.loads(match.group(0))


def suggest_accounts(category_hint: str = None) -> dict:
    """Get a diverse mix of 15 viral Instagram accounts across content types."""
    client = _get_client()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=(
            "You know currently viral Instagram accounts across many content types — "
            "sports, entertainment, movies, anime, music, comedy, gaming, celebrities, pop culture."
        ),
        messages=[{
            "role": "user",
            "content": (
                "List 15 currently VIRAL Instagram accounts, spread across DIVERSE content types.\n\n"
                "Requirements per account:\n"
                "- Real, well-known account (100K+ followers)\n"
                "- Every reel gets 100K+ likes\n"
                "- Actively posts short vertical video reels\n"
                "- English or international (not regional-language only)\n"
                "- No talking-head news accounts\n\n"
                "Include a mix from these types (at least 1-2 from each):\n"
                "- Sports highlights (NBA, football, F1, UFC, cricket)\n"
                "- Streamers/personalities (MrBeast, iShowSpeed, Kai Cenat, Speed, Adin Ross)\n"
                "- Movie/TV clips (edits, iconic scenes)\n"
                "- Anime edits (Naruto, One Piece, JJK, AOT, etc.)\n"
                "- Music/artist viral moments\n"
                "- Comedy/pranks/street interviews\n"
                "- Gaming/esports highlights\n"
                "- Celebrity/pop culture moments\n"
                "- Cars/luxury lifestyle\n"
                "- Fitness/motivational\n\n"
                "Return ONLY valid JSON, no other text:\n"
                '{"accounts": [\n'
                '  {"username": "mrbeast", "category": "MrBeast challenges"},\n'
                '  {"username": "nba", "category": "NBA highlights"},\n'
                '  ...\n'
                ']}\n'
                "Usernames only — no @ prefix."
            ),
        }],
    )

    try:
        result = _extract_json(message.content[0].text)
        raw_accounts = result.get("accounts", [])
        clean = []
        for a in raw_accounts:
            if isinstance(a, dict) and a.get("username"):
                clean.append({
                    "username": a["username"].lstrip("@").strip().lower(),
                    "category": a.get("category", "viral"),
                })
        if clean:
            return {"accounts": clean}
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  Claude returned non-JSON, using fallback: {e}")

    return {"accounts": [
        {"username": "mrbeast", "category": "MrBeast"},
        {"username": "nba", "category": "NBA"},
        {"username": "433", "category": "Football"},
        {"username": "ishow.speed", "category": "iShowSpeed"},
        {"username": "houseofhighlights", "category": "Basketball"},
        {"username": "marvel", "category": "Marvel"},
    ]}


def suggest_clip_hashtags(clip_title: str) -> list[str]:
    """Generate hashtags specific to this exact clip — show name, characters, genre."""
    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": (
            f"Generate 15 Instagram hashtags for a Reels clip about: \"{clip_title}\"\n\n"
            "Rules:\n"
            "- Must be SPECIFIC to this exact show/movie/character — no generic tags\n"
            "- Include: show/movie name, main characters, related shows in same genre, "
            "fandom tags, a few broad reach tags (reels, viral, fyp)\n"
            "- No spaces, lowercase, no # prefix\n"
            "- Good example for a Breaking Bad clip: breakingbad, walterwhite, heisenberg, "
            "jessepinkman, bettercallsaul, amc, crimeseries, tvshows, reels, viral\n\n"
            'Return ONLY: {"hashtags": ["tag1", ..., "tag15"]} — no # prefix.'
        )}],
    )
    try:
        result = _extract_json(message.content[0].text)
        tags = [t.lstrip("#").strip().lower().replace(" ", "") for t in result.get("hashtags", []) if t]
        if tags:
            return tags
    except (json.JSONDecodeError, ValueError):
        pass
    return ["reels", "viral", "fyp", "movieedits", "cinematicedits"]


def suggest_movie_queries() -> list[str]:
    """Ask Claude for YouTube search queries to find viral cinematic movie/TV clip edits."""
    client = _get_client()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": (
                f"Give me 10 YouTube search queries to find short viral clips (30–90 seconds) "
                f"from MOVIES, TV SHOWS, ANIME, or ANIMATED FILMS.\n\n"
                "STRICT RULES:\n"
                "- Each query MUST name a specific title, character, or scene\n"
                "- NO street interviews, NO memes, NO 'sigma male', NO reactions, NO pranks\n"
                "- EVERY response must be DIFFERENT — use your own knowledge, don't repeat titles run to run\n"
                "- Prefer titles you know have MASSIVE view counts on YouTube edits\n\n"
                f"This run's seed (use it to vary your picks): {random.randint(1, 9999)}\n\n"
                "Cover at least 5 DIFFERENT genres in the 10 queries. Genres to draw from:\n"
                "- Action / thriller movies\n"
                "- Crime / drama TV series\n"
                "- Anime (shonen, seinen, action-heavy)\n"
                "- Animated / Pixar / Dreamworks films\n"
                "- Sci-fi / superhero\n"
                "- Comedy TV series\n"
                "- Classic cinema\n\n"
                "Use whatever specific titles/characters YOU think are currently viral or timeless. "
                "Don't stick to the same ones every run.\n\n"
                "Return ONLY this JSON:\n"
                '{"queries": ["query1", "query2", ..., "query10"]}'
            ),
        }],
    )

    try:
        result = _extract_json(message.content[0].text)
        queries = [q.strip() for q in result.get("queries", []) if q]
        if queries:
            return queries
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  Claude non-JSON for movie queries: {e}")

    return [
        "joker edit 4k",
        "thomas shelby sigma edit",
        "walter white best scenes 4k",
        "dark knight joker scenes 4k",
        "breaking bad iconic moments edit",
        "inception cinematic edit",
        "peaky blinders best scenes",
        "godfather iconic scenes 4k",
        "interstellar cinematic edit",
        "arthur fleck joker transformation",
    ]


def suggest_brainrot_accounts() -> list[str]:
    """Ask Claude for Instagram accounts that post ONLY brainrot gameplay/crushing content."""
    client = _get_client()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=(
            "You know Instagram accounts that post specific gameplay recording content. "
            "Be extremely strict — only suggest accounts you're confident post ONLY the requested content type."
        ),
        messages=[{
            "role": "user",
            "content": (
                "Suggest 8 real Instagram accounts that post ONLY one of these content types:\n"
                "- Subway Surfers gameplay recordings (mobile game screen recording)\n"
                "- Minecraft PARKOUR GAMEPLAY (Minecraft video game — NOT real people)\n"
                "- Geometry Dash gameplay (2D neon geometric game)\n"
                "- Hydraulic press crushing videos\n"
                "- Satisfying crushing videos\n\n"
                "STRICT: ZERO real people, ZERO memes/cartoons/animations, ZERO tutorials/reactions.\n"
                "Must be actual video game footage or crushing footage only.\n\n"
                "Return ONLY valid JSON, no other text:\n"
                '{"accounts": ["username1", "username2", ...]}\n'
                "Usernames only — no @ prefix."
            ),
        }],
    )

    try:
        result = _extract_json(message.content[0].text)
        accounts = [a.lstrip("@").strip().lower() for a in result.get("accounts", []) if a]
        if accounts:
            return accounts
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  Claude returned non-JSON for brainrot, using fallback: {e}")

    return BRAINROT_FALLBACK
