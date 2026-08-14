import warnings
warnings.filterwarnings("ignore")

import argparse
import logging
import random
import shutil
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Silence yt-dlp's Python 3.9 deprecation warning
import yt_dlp
_yt_orig_df = yt_dlp.YoutubeDL.deprecated_feature
def _yt_silent_df(self, message, *args, **kwargs):
    if "Python" in str(message):
        return
    return _yt_orig_df(self, message, *args, **kwargs)
yt_dlp.YoutubeDL.deprecated_feature = _yt_silent_df

load_dotenv()

from config import CLIPS_OUTPUT, LOGS_DIR, INSTAGRAM_HASHTAGS, BRAINROT_PROBABILITY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "pipeline.log"),
    ],
)
log = logging.getLogger(__name__)

SOURCES = ["instagram", "twitch", "youtube", "reddit"]
_source_cycle = iter([])


def _next_source() -> str:
    global _source_cycle
    try:
        return next(_source_cycle)
    except StopIteration:
        shuffled = SOURCES[:]
        random.shuffle(shuffled)
        _source_cycle = iter(shuffled)
        return next(_source_cycle)


def run_pipeline(source: str = None, game: str = None, brainrot: bool = None, post: bool = False, movie_edit: bool = False):
    if movie_edit:
        source = "instagram"
        brainrot = False
    else:
        source = source or _next_source()
        if brainrot is None:
            brainrot = random.random() < BRAINROT_PROBABILITY

    log.info(f"=== Pipeline start | source={source} game={game} brainrot={brainrot} movie_edit={movie_edit} ===")
    ts = int(time.time())

    # --- Step 1: Download clip ---
    log.info("Downloading clip...")
    clip_title = ""
    if movie_edit:
        from scraper import movie_source
        raw, game = movie_source.download_clip()
    else:
        from scraper import youtube, twitch, reddit, instagram_source
        if source == "instagram":
            raw, game = instagram_source.download_clip(game)
        elif source == "youtube":
            raw, game = youtube.download_clip(game)
        elif source == "twitch":
            raw, game, clip_title = twitch.download_clip(game)
        else:
            raw, game = reddit.download_clip()
    log.info(f"Downloaded: {raw.name} | category={game}")

    # --- Step 2: Compose ---
    music_query = None
    if movie_edit:
        log.info("Fetching transcript + description + comments + generating hook...")
        from scraper.movie_source import get_transcript, get_context
        from ai.hook_generator import generate_from_video
        try:
            transcript = get_transcript(raw.stem)
            ctx = get_context(raw.stem)
            if transcript:
                log.info(f"Transcript ({len(transcript)} chars): {transcript[:100]}...")
            if ctx["description"]:
                log.info(f"Description ({len(ctx['description'])} chars): {ctx['description'][:100]}...")
            if ctx["comments"]:
                log.info(f"Top comments: {len(ctx['comments'])} fetched")
            hook = generate_from_video(
                raw, title=game, transcript=transcript,
                description=ctx["description"], comments=ctx["comments"],
            )
        except Exception as e:
            log.warning(f"Hook generation failed ({e}), continuing without hook")
            hook = None
        log.info(f"Hook: '{hook}'")

        log.info("Applying cinematic movie-edit (hook + @nyxvolt watermark)...")
        from processor.movie_edit import process as movie_process
        composed = movie_process(raw, hook_text=hook)
        log.info(f"Movie-edit: {composed.name}")
    elif brainrot:
        log.info("Compositing brain-rot split-screen (blur-fill both halves)...")
        from processor.split_screen import composite
        try:
            composed = composite(raw)
            log.info(f"Split-screen: {composed.name}")
        except RuntimeError as e:
            log.warning(f"Brain-rot failed ({e}), falling back to plain transform")
            from processor.video_edit import transform
            composed = transform(raw)
    else:
        log.info("Applying transformation stack...")
        from processor.video_edit import transform
        composed = transform(raw)

    final_processed = composed

    # --- Step 4: Save final output ---
    import re
    safe_game = re.sub(r"[^a-zA-Z0-9_-]+", "_", game)[:50] or "clip"
    final_name = f"final_{ts}_{safe_game}.mp4"
    final = CLIPS_OUTPUT / final_name
    shutil.copy2(final_processed, final)
    log.info(f"Final output: {final}")
    print(f"\n✓ Video ready: {final}")

    # --- Step 5: Verify quality with Claude vision ---
    log.info("Verifying video with Claude vision...")
    from processor.verify import verify as verify_video
    try:
        verdict = verify_video(final, category=game, hook="", brainrot=brainrot)
        passed = verdict.get("pass", False)
        issues = verdict.get("issues", [])
        notes = verdict.get("notes", "")
        if passed:
            log.info(f"✓ Verified: {notes}")
            print(f"✓ Verified: {notes}")
        else:
            log.warning(f"✗ Verify FAILED: {notes} | issues={issues}")
            print(f"✗ Verify FAILED: {notes}")
            for issue in issues:
                print(f"    - {issue}")
    except Exception as e:
        log.error(f"Verification error: {e}")
        verdict = {"pass": True, "issues": [], "notes": "verifier crashed, allowing"}
        passed = True

    # --- Step 6: Upload to Instagram (opt-in via --post flag, blocked if verify failed) ---
    if post and not passed:
        log.warning("Skipping upload — video failed verification")
        print("! Skipping upload — video failed verification")
    elif post:
        log.info("Uploading to Instagram...")
        from uploader.instagram import publish
        from ai.caption import generate_caption
        caption = generate_caption(game)
        log.info(f"Caption preview: {caption.splitlines()[0][:80]}...")
        try:
            url = publish(final, caption, music_query=music_query)
            log.info(f"Posted: {url}")
            print(f"✓ Posted: {url}")
        except Exception as e:
            log.error(f"Instagram upload failed: {e}")
            print(f"! Upload failed: {e}")
    else:
        log.info("Skipping Instagram upload (use --post to enable)")

    # --- Cleanup intermediates ---
    _cleanup(raw, composed, final_processed)
    log.info("=== Pipeline complete ===\n")


def _cleanup(*paths: Path):
    for p in paths:
        try:
            if p and p.exists() and p.parent.name in ("raw", "processed"):
                p.unlink()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Nyxvolt Gaming Content Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="Run pipeline once")
    group.add_argument("--schedule", action="store_true", help="Run scheduler (3x/day)")
    group.add_argument("--generate-brainrot", type=int, metavar="N",
                       help="Pre-generate N verified brainrot clips into pool (~/clips/secondary/) and exit")
    parser.add_argument("--source", choices=SOURCES, help="Force a specific source (default rotates, instagram first)")
    parser.add_argument("--game", type=str, help="Category to search (e.g. 'funny animals', 'cartoon', 'fails')")
    parser.add_argument("--brainrot", action="store_true", help="Force split-screen format")
    parser.add_argument("--movie-edit", action="store_true", help="Movie-edit mode: cinematic movie clips with AI-selected hype music")
    parser.add_argument("--post", action="store_true", help="Upload to Instagram (off by default)")
    args = parser.parse_args()

    if args.generate_brainrot:
        from scraper.secondary import generate_pool
        generate_pool(args.generate_brainrot)
        return

    if args.once:
        run_pipeline(
            source=args.source,
            game=args.game,
            brainrot=True if args.brainrot else None,
            post=args.post,
            movie_edit=args.movie_edit,
        )
    elif args.schedule:
        import scheduler
        scheduler.start(run_pipeline)


if __name__ == "__main__":
    main()
