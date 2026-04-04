import json
import logging

from openai import OpenAI, RateLimitError

from app.config import settings
from app.parser.base import ParsedEntry
from app.schemas import LLMParseResponse

logger = logging.getLogger(__name__)

# Flipped to True the moment we detect a quota-exhausted key so we stop
# trying on every message (the error won't resolve until the user tops up).
_quota_exhausted = False

SYSTEM = """You convert short food / drink / exercise logs into structured data.
Return ONLY valid JSON with this shape:
{"entries":[{"type":"food"|"drink"|"exercise","name":"short label","calories_in":null,"calories_out":null}]}

Rules:
- For food or drink, set calories_in to a reasonable estimate (integer kcal). calories_out must be null.
- For exercise, set calories_out to reasonable burned kcal. calories_in must be null.
- Use type "drink" for alcohol and beverages.
- Split multiple items into multiple objects (e.g. "2 beers and a wrap" -> two entries).
- If the user only gives a distance (e.g. ran 5km), estimate calories_out from typical burn.
- If truly unclear, make your best guess and note uncertainty in the name string.
"""


def parse(text: str) -> list[ParsedEntry] | None:
    """Returns parsed entries, or None if the API is unavailable or parsing failed."""
    global _quota_exhausted
    if not settings.openai_api_key or _quota_exhausted:
        return None
    try:
        client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        validated = LLMParseResponse.model_validate(data)
        return [
            ParsedEntry(
                e.type,
                e.name or e.type,
                calories_in=e.calories_in,
                calories_out=e.calories_out,
            )
            for e in validated.entries
        ]
    except RateLimitError as e:
        if "insufficient_quota" in str(e):
            _quota_exhausted = True
            logger.warning(
                "OpenAI quota exhausted — LLM parsing disabled for this session. "
                "Top up at https://platform.openai.com/account/billing or remove OPENAI_API_KEY."
            )
        else:
            logger.warning("OpenAI rate-limited (temporary): %s", e)
        return None
    except Exception as e:
        logger.warning("LLM parse failed, falling back to regex: %s", e)
        return None
