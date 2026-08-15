import os
import anthropic

_client = None
BRAND_FOOTER = "Daily movie edits by @nyxvolt"


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def generate_caption(category: str) -> str:
    """Generate an engagement-driving Instagram caption + append hashtags."""
    client = _get_client()

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=(
            "You write Instagram Reels captions engineered to maximize COMMENTS. "
            "Style: 2 short lines. First line is a punchy statement or opinion about the clip. "
            "Second line is a question that begs a comment reply. "
            "Rules:\n"
            "- Questions must be specific and easy to answer (rating, favorite, choice, tag someone)\n"
            "- 1-2 tasteful emojis max (fire, cinema, skull, brain, no random ones)\n"
            "- NO hashtags in the body, NO generic 'follow for more'\n"
            "- End with the question so it invites a response\n"
            "- NEVER use em dashes (—) or en dashes (–). Use commas, periods, or line breaks instead. "
            "This is critical: em dashes make posts look AI-generated and hurt reach."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Write an engagement caption for a movie/TV edit reel about '{category}'.\n\n"
                "Good question styles (pick one):\n"
                "- Rate this scene 1-10\n"
                "- Which character would you be?\n"
                "- Tag someone who reminds you of him\n"
                "- Best line ever or overrated?\n"
                "- Which show hits harder, X or Y?\n"
                "- What's your favorite scene from this?\n\n"
                "Output ONLY the 2-line caption. No hashtags, no quotes, no preamble."
            ),
        }],
    )

    caption_text = message.content[0].text.strip().strip('"').strip("'")
    # Strip em/en dashes (AI tells) — replace with comma
    caption_text = caption_text.replace("—", ",").replace("–", ",")

    from ai.trending import suggest_clip_hashtags
    tags = suggest_clip_hashtags(category)
    hashtag_str = " ".join(f"#{t}" for t in tags)

    return f"{caption_text}\n\n{BRAND_FOOTER}\n\n{hashtag_str}"
