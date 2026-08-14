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


def suggest_movie_hashtags() -> list[str]:
    """Ask Claude for movie/TV/character hashtags to discover viral accounts."""
    client = _get_client()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": (
            "List 10 Instagram hashtags for viral movie/TV clip edits. "
            "Mix general (movieedits, sigmaedits), movie names (inceptionedit, peakyblinders), "
            "and character names (joker, heisenberg, thomasshelby).\n"
            'Return ONLY: {"hashtags": ["tag1", ..., "tag10"]} — no # prefix.'
        )}],
    )
    try:
        result = _extract_json(message.content[0].text)
        tags = [t.lstrip("#").strip().lower().replace(" ", "") for t in result.get("hashtags", []) if t]
        if tags:
            return tags
    except (json.JSONDecodeError, ValueError):
        pass
    return ["movieedits", "sigmaedits", "joker", "heisenberg", "thomasshelby",
            "peakyblinders", "breakingbad", "inceptionedit", "cinematicedits", "filmedits"]


def suggest_movie_queries() -> list[str]:
    """Ask Claude for YouTube search queries to find viral cinematic movie/TV clip edits."""
    client = _get_client()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": (
                "Give me 10 YouTube search queries to find short viral CINEMATIC clips from "
                "MOVIES or TV SHOWS ONLY (30–90 seconds).\n\n"
                "STRICT RULES:\n"
                "- ONLY real movies/TV shows (e.g. Peaky Blinders, Breaking Bad, Dark Knight, John Wick)\n"
                "- Each query MUST include a specific movie/show/character name\n"
                "- NO street interviews, NO memes, NO 'sigma male' compilations, NO reactions, NO pranks\n"
                "- NO general vibe queries like 'sigma edit' — always tie to a specific movie/character\n\n"
                "Good examples:\n"
                "  'peaky blinders tommy shelby edit 4k'\n"
                "  'dark knight joker interrogation scene'\n"
                "  'john wick action scene edit'\n"
                "  'breaking bad walter white transformation scene'\n"
                "  'gladiator maximus edit 4k'\n\n"
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
