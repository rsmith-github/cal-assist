import logging

from app.nutrition import open_food_facts as off
from app.parser import llm_parser, regex_parser
from app.parser.base import ParsedEntry

logger = logging.getLogger(__name__)


def parse_log_line(text: str) -> list[ParsedEntry]:
    """OpenAI (if configured) → local regex/JSON → Open Food Facts (if enabled)."""
    llm_result = llm_parser.parse(text)
    if llm_result is not None and len(llm_result) > 0:
        return llm_result
    rx = regex_parser.parse(text)
    if rx:
        return rx
    if not off.skip_off_lookup(text):
        off_entries = off.lookup_as_entries(text)
        if off_entries:
            return off_entries
    logger.debug("No parser matched: %s", text[:80])
    return []
