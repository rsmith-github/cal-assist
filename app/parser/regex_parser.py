import json
import re
from pathlib import Path

from app.parser.base import ParsedEntry

# Spoken-number → integer for quantities like "five eggs", "two beers"
_WORD_NUMS: dict[str, int | float] = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "half": 0.5,
}

# Volume/weight units that mean the leading number is a measure, not a count.
# e.g. "500 ml orange juice" → 1 serving, not 500 servings.
_MEASURE_UNIT_RE = re.compile(
    r"(?i)^(ml|cl|dl|l|g|kg|oz|lb|lbs|cup|cups|serving|servings|portion|slice|piece|pieces)\s+"
)
_WORD_NUM_RE = re.compile(
    r"(?i)^(a|an|one|two|three|four|five|six|seven|eight|nine|ten|half)\s+(.+)$"
)
_WORD_NUM_WITH_VERB_RE = re.compile(
    r"(?i)^(?:had|ate|drank)\s+(a|an|one|two|three|four|five|six|seven|eight|nine|ten|half)\s+(.+)$"
)

_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "known_foods.json"


def _load_tables() -> tuple[dict, dict, dict[str, str]]:
    raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    items = raw.get("items", {})
    exercise_rates = raw.get("exercise_rates", {})
    alias_to_key: dict[str, str] = {}

    for key, meta in items.items():
        alias_to_key[key.lower()] = key
        for a in meta.get("aliases", []):
            alias_to_key[a.lower()] = key

    for key, meta in exercise_rates.items():
        alias_to_key[key.lower()] = f"ex:{key}"
        for a in meta.get("aliases", []):
            alias_to_key[a.lower()] = f"ex:{key}"

    return items, exercise_rates, alias_to_key


_ITEMS, _EX_RATES, _ALIASES = _load_tables()


def _resolve_item_key(phrase: str) -> str | None:
    p = phrase.strip().lower().rstrip(".")
    if p in _ALIASES:
        return _ALIASES[p]
    candidates: list[tuple[int, str]] = []
    for alias, key in _ALIASES.items():
        if not alias:
            continue
        # Use word-boundary matching so "cola" doesn't match inside "chocolate"
        alias_esc = re.escape(alias)
        if re.search(r"(?<!\w)" + alias_esc + r"(?!\w)", p) or re.search(
            r"(?<!\w)" + re.escape(p) + r"(?!\w)", alias
        ):
            candidates.append((len(alias), key))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def _parse_exercise_line(s: str) -> list[ParsedEntry]:
    s_low = s.lower()
    for ex_key, rates in _EX_RATES.items():
        names = [ex_key.lower(), *[a.lower() for a in rates.get("aliases", [])]]
        if not any(n in s_low for n in names if n):
            continue
        per_km = rates.get("kcal_per_km")
        per_hr = rates.get("kcal_per_hour")
        if per_km is not None:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:km|kms|k)\b", s, re.I)
            dist = float(m.group(1)) if m else None
            if dist is None:
                m2 = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:mile|miles)\b", s, re.I)
                if m2:
                    dist = float(m2.group(1)) * 1.609
            if dist is not None:
                out = int(round(dist * per_km))
                label = f"{ex_key} {dist:g} km"
                return [
                    ParsedEntry(
                        "exercise",
                        label,
                        calories_out=max(out, 1),
                    )
                ]
        if per_hr is not None:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:hr|h|hrs|hours?)\b", s, re.I)
            if m:
                hrs = float(m.group(1))
                label = f"{ex_key} {hrs:g} hr"
            else:
                # Try word numbers: "six hours muay thai", "two hrs gym"
                wm = re.search(
                    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|half)"
                    r"\s+(?:hr|h|hrs|hours?)\b",
                    s,
                    re.I,
                )
                if wm:
                    hrs = float(_WORD_NUMS[wm.group(1).lower()])
                    label = f"{ex_key} {hrs:g} hr"
                else:
                    hrs = 1.0
                    label = f"{ex_key} (~1 hr)"
            out = int(round(hrs * per_hr))
            return [ParsedEntry("exercise", label, calories_out=max(out, 1))]
    return []


def _parse_kcal_line(s: str) -> list[ParsedEntry]:
    burn = bool(re.search(r"\b(burn(?:ed|ing)?|workout|exercise)\b", s, re.I))
    nums = list(
        re.finditer(
            r"(\d+)\s*(?:kcal|cals|calories|cal)\b",
            s,
            re.I,
        )
    )
    if not nums:
        return []
    # Use first number as primary; rest ignored unless we add multi later
    n = int(nums[0].group(1))
    rest = s[nums[0].end() :].strip()
    if burn or re.search(r"\b(out|burned)\b", s, re.I):
        label = rest or "exercise"
        return [ParsedEntry("exercise", label[:80], calories_out=n)]
    label = rest or "food"
    is_drink = bool(re.search(r"\b(beer|wine|drink|soda|coffee|latte|shot)\b", label, re.I))
    return [
        ParsedEntry(
            "drink" if is_drink else "food",
            label[:80],
            calories_in=n,
        )
    ]


def _parse_quantity_item(count: int, item_phrase: str) -> list[ParsedEntry]:
    key = _resolve_item_key(item_phrase)
    if not key or key.startswith("ex:"):
        return []
    real_key = key
    meta = _ITEMS[real_key]
    cal = meta["calories_each"] * count
    t = meta.get("type", "food")
    return [ParsedEntry(t, f"{count}x {real_key}", calories_in=cal)]


def _parse_segment(seg: str) -> list[ParsedEntry]:
    s = seg.strip()
    if not s:
        return []

    ex = _parse_exercise_line(s)
    if ex:
        return ex

    kc = _parse_kcal_line(s)
    if kc:
        return kc

    # "had 3 eggs" / "ate 2 burgers"
    m = re.match(r"(?i)(?:had|ate|drank)\s+(\d+)\s+(.+)$", s)
    if m:
        q = _parse_quantity_item(int(m.group(1)), m.group(2))
        if q:
            return q

    # "had two beers" / "ate a burger"
    m = _WORD_NUM_WITH_VERB_RE.match(s)
    if m:
        qty = _WORD_NUMS[m.group(1).lower()]
        q = _parse_quantity_item(qty, m.group(2))
        if q:
            return q

    # "3 eggs" — but skip if the number is actually a measure ("500 ml orange juice")
    m = re.match(r"(?i)^(\d+)\s+(.+)$", s)
    if m and not _MEASURE_UNIT_RE.match(m.group(2)):
        q = _parse_quantity_item(int(m.group(1)), m.group(2))
        if q:
            return q

    # "five eggs" / "two beers" / "a coffee"
    m = _WORD_NUM_RE.match(s)
    if m:
        qty = _WORD_NUMS[m.group(1).lower()]
        q = _parse_quantity_item(qty, m.group(2))
        if q:
            return q

    key = _resolve_item_key(s)
    if key and not key.startswith("ex:"):
        return _parse_quantity_item(1, s)

    return []


def parse(text: str) -> list[ParsedEntry]:
    """Regex + lookup-table parse. Returns zero items if nothing matched."""
    raw = text.strip()
    if not raw:
        return []

    segments = re.split(r"\s+and\s+", raw, flags=re.I)
    out: list[ParsedEntry] = []
    for seg in segments:
        part = re.split(r",\s*", seg)
        for p in part:
            got = _parse_segment(p.strip())
            out.extend(got)
    return out
