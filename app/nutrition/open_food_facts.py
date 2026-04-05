"""
Fallback nutrition lookup via Open Food Facts (free, no API key).

See https://openfoodfacts.github.io/openfoodfacts-server/api/ — use a descriptive User-Agent.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

import httpx

from app.config import settings
from app.parser.base import ParsedEntry

logger = logging.getLogger(__name__)

SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"

# Skip OFF when the line clearly looks like exercise (regex already failed).
_EXERCISE_HINT = re.compile(
    r"\b(run|ran|running|jog|walk|walked|bike|cycle|swim|gym|lift|workout|"
    r"hiit|yoga|muay|boxing|km|kms|mile|miles|hr|hrs|hour|hours|burn(?:ed|ing)?|"
    r"calories?\s+out)\b",
    re.I,
)


def skip_off_lookup(text: str) -> bool:
    return bool(_EXERCISE_HINT.search(text.strip()))


_MEASURE_PREFIX_RE = re.compile(
    r"(?i)^(\d+(?:\.\d+)?)\s*(ml|cl|dl|l|g|kg|oz|lb|lbs|cup|cups)\s+(.+)$"
)


def _clean_query(text: str) -> tuple[int, str]:
    """Strip logging filler and optional leading quantity: (count, search phrase)."""
    t = text.strip()
    t = re.sub(r"(?i)^(had|ate|drank)\s+", "", t)
    # Strip measure prefix ("200ml orange juice" → "orange juice") so the
    # search term is just the food name.
    mm = _MEASURE_PREFIX_RE.match(t)
    if mm:
        return 1, mm.group(3).strip()
    m = re.match(r"(?i)^(\d+)\s*[x×]\s+(.+)$", t)
    if m:
        return max(1, int(m.group(1))), m.group(2).strip()
    m = re.match(r"(?i)^(\d+)\s+(.+)$", t)
    if m and not re.match(r"^\d+\s*(?:kcal|cals|calories|cal)\b", t, re.I):
        return max(1, int(m.group(1))), m.group(2).strip()
    return 1, t


def _kcal_from_product(product: dict[str, Any]) -> int | None:
    n = product.get("nutriments") or {}
    if not isinstance(n, dict):
        return None

    for key in (
        "energy-kcal_serving",
        "energy_serving_prepared_kcal",
        "energy-kcal-prepared_serving",
    ):
        v = n.get(key)
        if v is not None:
            try:
                return max(1, int(round(float(v))))
            except (TypeError, ValueError):
                pass

    v = n.get("energy-kcal")
    if v is not None:
        try:
            return max(1, int(round(float(v))))
        except (TypeError, ValueError):
            pass

    v100 = n.get("energy-kcal_100g")
    if v100 is not None:
        try:
            # Rough: treat as one 100 g portion if no serving data.
            return max(1, int(round(float(v100))))
        except (TypeError, ValueError):
            pass

    return None


def _entry_type_from_product(product: dict[str, Any]) -> str:
    tags = product.get("categories_tags") or []
    if not isinstance(tags, list):
        return "food"
    joined = " ".join(str(t).lower() for t in tags)
    if "beverage" in joined or "drink" in joined or "alcohol" in joined:
        return "drink"
    return "food"


@lru_cache(maxsize=128)
def _search_first_kcal(query_normalized: str) -> tuple[int, str, str] | None:
    """Returns (kcal_per_unit, product_label, entry_type) or None."""
    contact = (settings.off_contact_url or "https://github.com").strip()
    headers = {
        "User-Agent": f"Cal-Assist/1.0 ({contact})",
        "Accept": "application/json",
    }
    params = {
        "search_terms": query_normalized,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 5,
    }
    try:
        with httpx.Client(timeout=settings.off_request_timeout_sec) as client:
            r = client.get(SEARCH_URL, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        logger.warning(
            "Open Food Facts HTTP %s for query=%r",
            e.response.status_code,
            query_normalized[:60],
        )
        return None
    except Exception as e:
        logger.warning(
            "Open Food Facts request failed for query=%r: %s",
            query_normalized[:60],
            e,
        )
        return None

    products = data.get("products") or []
    if not isinstance(products, list):
        return None

    for product in products:
        if not isinstance(product, dict):
            continue
        kcal = _kcal_from_product(product)
        if kcal is None:
            continue
        name = (product.get("product_name") or query_normalized).strip() or query_normalized
        et = _entry_type_from_product(product)
        return kcal, name[:120], et

    return None


def lookup_as_entries(user_text: str) -> list[ParsedEntry]:
    """Resolve a single free-text line to entries using OFF, or []."""
    if not settings.open_food_facts_enabled:
        return []
    if skip_off_lookup(user_text):
        return []

    qty, query = _clean_query(user_text)
    q = query.strip()
    if len(q) < 2:
        return []

    hit = _search_first_kcal(q.lower())
    if not hit:
        return []

    kcal_unit, label, et = hit
    total = max(1, kcal_unit * qty)
    detail = f"{qty}x {label}" if qty > 1 else label
    detail = f"{detail} (~{total} kcal, Open Food Facts)"
    return [ParsedEntry(et, detail, calories_in=total)]


def clear_search_cache() -> None:
    """For tests."""
    _search_first_kcal.cache_clear()
