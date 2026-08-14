import os
import random
import praw
import yt_dlp
from pathlib import Path
from config import CLIPS_RAW, REDDIT_SUBS


def download_clip() -> tuple[Path, str]:
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", "nyxvolt-bot/1.0"),
    )

    sub_name = random.choice(REDDIT_SUBS)
    sub = reddit.subreddit(sub_name)
    posts = list(sub.top(time_filter="day", limit=50))
    video_posts = [p for p in posts if _is_video(p)]

    if not video_posts:
        raise RuntimeError(f"No video posts found in r/{sub_name} today")

    post = random.choice(video_posts[:15])
    url = post.url
    game = _guess_game(post.title)

    output_path = CLIPS_RAW / "%(id)s.%(ext)s"
    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio/best[ext=mp4]/best",
        "outtmpl": str(output_path),
        "quiet": True,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded = Path(ydl.prepare_filename(info))

    return downloaded, game


def _is_video(post) -> bool:
    return (
        post.is_video
        or "v.redd.it" in post.url
        or "clips.twitch.tv" in post.url
        or "youtube.com" in post.url
        or "youtu.be" in post.url
    )


def _guess_game(title: str) -> str:
    title_lower = title.lower()
    keywords = {
        "god of war": ["god of war", "kratos"],
        "call of duty": ["cod", "warzone", "call of duty", "mw3"],
        "gta 5": ["gta", "grand theft"],
        "fortnite": ["fortnite"],
        "minecraft": ["minecraft"],
        "elden ring": ["elden ring"],
        "valorant": ["valorant"],
    }
    for game, terms in keywords.items():
        if any(t in title_lower for t in terms):
            return game
    return "gaming"
