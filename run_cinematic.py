import argparse
import logging
import sys
import warnings

warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv()

from config import LOGS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOGS_DIR / "ai_cinematic.log"),
    ],
)


def main():
    parser = argparse.ArgumentParser(
        description="Nyxvolt AI cinematic pipeline (Gemini images + Ken Burns + edge-tts narration + burned subtitles)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 run_cinematic.py --once                                    # Claude picks the topic\n"
            "  python3 run_cinematic.py --once \"what if the light bulb was never invented\"\n"
            "  python3 run_cinematic.py --once \"what if humans could fly\" --post"
        ),
    )
    parser.add_argument("--once", action="store_true", required=True,
                       help="Generate one reel and exit")
    parser.add_argument("--post", action="store_true",
                       help="Upload to Instagram after generation")
    parser.add_argument("--keep", action="store_true",
                       help="Keep intermediate files (images, per-scene clips) for debugging")
    parser.add_argument("topic", nargs="?", default=None,
                       help="Optional 'what if' topic in quotes. If omitted, Claude picks one.")
    args = parser.parse_args()

    from ai_cinematic.pipeline import run
    out = run(post=args.post, keep_intermediates=args.keep, topic=args.topic)
    print(f"\n✓ Video ready: {out}")


if __name__ == "__main__":
    main()
