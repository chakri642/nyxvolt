import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

CLIPS_RAW = BASE_DIR / "clips" / "raw"
CLIPS_PROCESSED = BASE_DIR / "clips" / "processed"
CLIPS_OUTPUT = BASE_DIR / "clips" / "output"
CLIPS_SECONDARY = BASE_DIR / "clips" / "secondary"
MUSIC_DIR = BASE_DIR / "music"
LOGS_DIR = BASE_DIR / "logs"

CLIP_MIN_DURATION = 30
CLIP_MAX_DURATION = 55
PEAK_LEAD_SECONDS = 4
PEAK_TAIL_SECONDS = 36

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30

SPEED_FACTOR = 1.05
SATURATION = 1.3
CONTRAST = 1.1
ZOOM_FACTOR = 1.12
AUDIO_DUCK_LEVEL = 0.15
FLASH_DURATION = 0.3

SCHEDULE_HOURS = [9, 13, 19]
BRAINROT_PROBABILITY = 0.4

GAMES = [
    "god of war",
    "call of duty",
    "gta 5",
    "elden ring",
    "spider-man ps5",
    "fortnite",
    "valorant",
    "minecraft",
]

INSTAGRAM_HASHTAGS = (
    "#viral #trending #reels #fyp #foryou "
    "#viralreels #trendingreels #explore #instareels #reelitfeelit "
    "#mrbeast #ishowspeed #anime #movies #footballclips"
)

TWITCH_GAME_IDS = {
    "call of duty": "512710",
    "fortnite": "33214",
    "minecraft": "27471",
    "valorant": "516575",
    "gta 5": "32982",
    "apex legends": "511224",
    "league of legends": "21779",
    "cs2": "32399",
    "rocket league": "30921",
    "elden ring": "65897",
    "god of war": "512710",
    "fifa": "1745202732",
    "overwatch 2": "515025",
}

REDDIT_SUBS = ["gaming", "clips", "GamePhysics", "unexpected"]
