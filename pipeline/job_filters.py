#!/usr/bin/env python3
"""Free pre-LLM filters — title skip list and geographic scope.

Both classify_jobs.py and fetch_job_descriptions.py use these so a job that
will never reach the board also never costs a description fetch or an LLM call.

Geographic scope is currently remote + Colorado. `classify_location()` returns
one of:

    remote        — a remote role with no non-US/Canada restriction  → classify
    colorado      — an on-site or hybrid role in Colorado            → classify
    ambiguous     — no usable signal in the ATS location field       → classify
    international — requires presence outside the US / Canada        → skip
    elsewhere     — a specific location outside the wanted scope     → skip

"ambiguous" is deliberately kept in scope: values like "United States",
"Multiple Locations", or an empty field often hide a remote role whose
remote-ness is only stated in the description, and only the LLM can see that.

WIDENING THE SCOPE LATER
    1. Add to WANTED_STATE_CODES / WANTED_PLACES below (or add a scope regex).
    2. Purge the jobs already cached as out-of-scope so they get reconsidered:
           PYTHONPATH=. python pipeline/classify_jobs.py --purge-skips location
    3. The next run reclassifies them at normal cost.
"""

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
TITLE_SKIP_FILE = DATA_DIR / "job_title_skip_patterns.json"

SKIP_REASON_TITLE = "title"
SKIP_REASON_LOCATION = "location"

_TITLE_SKIP_PATTERNS: tuple[str, ...] = tuple(
    json.loads(TITLE_SKIP_FILE.read_text()) if TITLE_SKIP_FILE.exists() else []
)


def title_is_skip(title: str) -> bool:
    t = title.lower()
    return any(p in t for p in _TITLE_SKIP_PATTERNS)


# --- Geographic scope ------------------------------------------------------

_INTL_LOCATION_RE = re.compile(
    r"\b("
    # Europe
    r"france|germany|spain|italy|netherlands|belgium|sweden|norway|denmark|finland|"
    r"poland|czech|austria|switzerland|portugal|ireland|united kingdom|"
    r"scotland|england|wales|greece|turkey|ukraine|romania|hungary|serbia|"
    r"croatia|slovakia|slovenia|bulgaria|latvia|lithuania|estonia|"
    # Asia-Pacific
    r"india|singapore|japan|south korea|china|australia|new zealand|"
    r"vietnam|thailand|malaysia|indonesia|philippines|taiwan|hong kong|"
    # Middle East / Africa
    r"israel|uae|dubai|saudi arabia|qatar|egypt|nigeria|kenya|south africa|"
    # Latin America
    r"mexico|brazil|colombia|chile|argentina|peru|"
    # Regional names and codes
    r"europe|european union|britain|uk|gb|asia|africa|middle east|oceania|"
    r"caribbean|latin america|south america|benelux|nordics|iberia|"
    r"emea|apac|apj|anz|latam|dach"
    r")\b",
    re.IGNORECASE,
)

# If a US/Canada indicator is present, don't treat it as international even when
# an international name also appears (e.g. "San Francisco, CA / London, UK").
# "New Mexico" listed explicitly because \bmexico\b would otherwise match it.
_US_SAFE_TEXT_RE = re.compile(
    r"\bUnited States\b|\bUSA\b|\bU\.S\.A?\.|\bNew Mexico\b", re.IGNORECASE
)

# State codes are matched case-SENSITIVELY on purpose: lowercased, a dozen of
# them are ordinary English words ("or", "in", "me", "hi", "ok", "de", "la"),
# and "Cardiff, London or Remote (UK)" then reads as Oregon. ATS location
# fields write state codes uppercase. A code at the very start of the string is
# not accepted either, since that position is where country codes live
# ("ES - Barcelona, Spain", "DE - Munich, Germany").
_US_STATE_CODE_RE = re.compile(
    r"[,/;|(\s](?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|"
    r"NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)"
    r"(?=[,/;|)\s.]|$)"
)


def _has_us_marker(loc: str) -> bool:
    return bool(_US_SAFE_TEXT_RE.search(loc) or _US_STATE_CODE_RE.search(loc))

_REMOTE_RE = re.compile(
    r"\bremote(?:ly)?\b|\bwork\s?from\s?home\b|\bwfh\b|\bhome[\s-]based\b"
    r"|\banywhere\b|\bdistributed\b|\btelecommut\w*\b|\btelework\b|\bvirtual\b",
    re.IGNORECASE,
)

# Two-letter state codes in scope. Matched case-sensitively so a lowercase
# word like "co" inside prose can't pass for Colorado.
WANTED_STATE_CODES = ("CO",)

_STATE_CODE_RE = re.compile(
    r"(?:^|[\s,/;(|·-])(?:" + "|".join(WANTED_STATE_CODES) + r")(?=[\s,/;)|·.-]|$)"
)

# Place names distinctive enough to imply the state on their own. Names that are
# common in other states (Aurora, Louisville, Golden, Superior, Erie, Parker,
# Frisco, Windsor, Lafayette, Brighton) are deliberately absent — those still
# match via the "CO" state code, which real postings almost always include.
WANTED_PLACES = (
    "colorado",
    "denver",
    "boulder",
    "fort collins",
    "broomfield",
    "longmont",
    "loveland",
    "greeley",
    "arvada",
    "centennial",
    "englewood",
    "greenwood village",
    "highlands ranch",
    "lone tree",
    "littleton",
    "lakewood",
    "wheat ridge",
    "northglenn",
    "thornton",
    "commerce city",
    "castle rock",
    "steamboat springs",
    "durango",
    "grand junction",
    "pueblo",
    "aspen",
    "vail",
    "breckenridge",
    "telluride",
    "fort carson",
    "buckley space force base",
)

_PLACE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in WANTED_PLACES) + r")\b",
    re.IGNORECASE,
)

# Location strings carrying no usable geographic signal.
_NO_SIGNAL_VALUES = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "none",
        "null",
        "tbd",
        "unknown",
        "unspecified",
        "not specified",
        "no location",
        "various",
        "multiple",
        "field",
        "field based",
        "us",
        "u.s.",
        "usa",
        "u.s.a.",
        "united states",
        "united states of america",
        "north america",
        "americas",
        "amer",
        "namer",
        "nam",
        "nationwide",
        "canada",
    }
)

_NO_SIGNAL_RE = re.compile(
    r"multiple location|various location|several location|multiple office"
    r"|\bblank\b|\bnationwide\b|\bmultiple\s+cities\b",
    re.IGNORECASE,
)


def is_international(location: str | None) -> bool:
    if not location:
        return False
    loc = location.strip()
    if not loc or loc.lower() == "remote":
        return False
    if _has_us_marker(loc):
        return False
    return bool(_INTL_LOCATION_RE.search(loc))


def _has_no_signal(loc: str) -> bool:
    bare = loc.strip().lower()
    # Collapse separators too, so "US, Remote"-style punctuation doesn't hide a
    # no-signal value like "United States / USA".
    collapsed = re.sub(r"[\s,/;|]+", " ", bare).strip()
    if bare in _NO_SIGNAL_VALUES or collapsed in _NO_SIGNAL_VALUES:
        return True
    return bool(_NO_SIGNAL_RE.search(loc))


def classify_location(location: str | None) -> str:
    """Return remote / colorado / ambiguous / international / elsewhere."""
    loc = (location or "").strip()
    if not loc or _has_no_signal(loc):
        return "ambiguous"
    if is_international(loc):
        return "international"
    if _REMOTE_RE.search(loc):
        return "remote"
    if _STATE_CODE_RE.search(loc) or _PLACE_RE.search(loc):
        return "colorado"
    return "elsewhere"


IN_SCOPE = frozenset({"remote", "colorado", "ambiguous"})


def location_in_scope(location: str | None) -> bool:
    """True if this job is worth spending a description fetch and an LLM call on."""
    return classify_location(location) in IN_SCOPE


def job_in_scope(job: dict) -> bool:
    return not title_is_skip(job.get("title", "")) and location_in_scope(job.get("location"))
