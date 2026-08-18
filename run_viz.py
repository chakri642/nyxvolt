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
        logging.FileHandler(LOGS_DIR / "data_viz.log"),
    ],
)


def main():
    parser = argparse.ArgumentParser(description="Nyxvolt data-viz pipeline (line chart + events + voice)")
    parser.add_argument("--once", action="store_true", help="Generate one video and exit")
    parser.add_argument("--no-voice", action="store_true", help="Skip voiceover (silent video)")
    parser.add_argument("--post", action="store_true", help="Upload to Instagram (off by default)")
    args = parser.parse_args()

    if not args.once:
        parser.error("Must pass --once for now (scheduler support later)")

    from data_viz.pipeline import run
    out = run(voice=not args.no_voice, post=args.post)
    print(f"\n✓ Video ready: {out}")


if __name__ == "__main__":
    main()
