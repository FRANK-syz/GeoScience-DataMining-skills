"""Shared helpers for the geo-literature-download-skill pipeline.

Locates the task workspace from ``LIT_ROOT`` or the current working directory.

Provides: audit logging (JSONL + resumable state), filename sanitisation,
PDF/HTML full-text verification and polite downloading.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import random
import re
import time
import unicodedata
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
ROOT = os.environ.get("LIT_ROOT") or os.getcwd()
BREAKPOINT_DIR = os.path.join(ROOT, "breakpoint")
LITERATURE_DIR = os.path.join(ROOT, "literature")
OUTPUT_DIR = os.path.join(ROOT, "output")
SCRIPTS_DIR = os.path.join(ROOT, "scripts")

# Hard limits of this skill.
MAX_SEARCH_TERMS = 6
# Hard boundary: the run stops the moment the cumulative success count
# reaches this cap, so literature/ can never exceed it.
HARD_STOP_SUCCESSES = 80
MAX_SUCCESSES = HARD_STOP_SUCCESSES
DEFAULT_TARGET = 50

AUDIT_FILE = os.path.join(BREAKPOINT_DIR, "audit_log.jsonl")
STATE_FILE = os.path.join(BREAKPOINT_DIR, "state.json")
SEARCH_INFO_CSV = os.path.join(OUTPUT_DIR, "literature_search_info.csv")
INVENTORY_CSV = os.path.join(OUTPUT_DIR, "literature_download_inventory.csv")
SEARCH_TERMS_FILE = os.path.join(BREAKPOINT_DIR, "search_terms.json")
TOPIC_FILE = os.path.join(BREAKPOINT_DIR, "topic_analysis.json")
HARVEST_FILE = os.path.join(BREAKPOINT_DIR, "harvest_raw.json")
CANDIDATES_FILE = os.path.join(BREAKPOINT_DIR, "candidates.json")
QUEUE_FILE = os.path.join(BREAKPOINT_DIR, "script_queue.json")
BROWSER_QUEUE_FILE = os.path.join(BREAKPOINT_DIR, "browser_queue.json")
RESULTS_FILE = os.path.join(BREAKPOINT_DIR, "download_results.json")
BROWSER_RESULTS_FILE = os.path.join(BREAKPOINT_DIR, "browser_results.json")
EXCLUSIONS_FILE = os.path.join(BREAKPOINT_DIR, "exclusions.json")


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def audit(step: str, action: str, detail: str = "", **extra) -> dict:
    """Append one audit record; also echo to stdout for the transcript."""
    rec = {
        "ts": now_iso(),
        "agent": "geo-literature-download-skill",
        "step": step,
        "action": action,
        "detail": detail,
    }
    if extra:
        rec["data"] = extra
    os.makedirs(BREAKPOINT_DIR, exist_ok=True)
    with open(AUDIT_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def ensure_dirs() -> None:
    for d in (BREAKPOINT_DIR, LITERATURE_DIR, OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_state(state: dict) -> None:
    os.makedirs(BREAKPOINT_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def load_json(path: str, default=None):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return default


def save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------------------------------------------------------------- filenames
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(index: int, title: str, max_len: int = 110) -> str:
    """`NNN_clean-title.pdf` - lowercase, no Windows-illegal chars, stable."""
    t = html.unescape(title or "untitled")
    t = unicodedata.normalize("NFKC", t)
    t = _ILLEGAL.sub(" ", t)
    t = t.replace("&", " and ")
    t = re.sub(r"[^\w\s\-\u4e00-\u9fff]", " ", t)
    t = re.sub(r"[\s_]+", " ", t).strip()
    t = re.sub(r"\s*-\s*", "-", t)
    t = t.lower()
    if len(t) > max_len:
        t = t[:max_len].rstrip()
    t = t.rstrip(". ")
    if not t:
        t = "untitled"
    return f"{index:03d}_{t}.pdf"


def unique_path(directory: str, filename: str) -> str:
    """Never overwrite an unrelated file: append a stable hash suffix."""
    path = os.path.join(directory, filename)
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(filename)
    digest = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:6]
    cand = os.path.join(directory, f"{stem}-{digest}{ext}")
    n = 2
    while os.path.exists(cand):
        cand = os.path.join(directory, f"{stem}-{digest}-{n}{ext}")
        n += 1
    return cand


# ---------------------------------------------------------------- politeness
def polite_sleep(low: float = 15.0, high: float = 30.0, label: str = "") -> float:
    """Random 15-30 s pause between requests to avoid rate limiting."""
    secs = random.uniform(low, high)
    audit("politeness", "sleep", f"waiting {secs:.1f}s before request {label}".strip(),
          low=low, high=high)
    time.sleep(secs)
    return secs


# ---------------------------------------------------------------- pdf check
_PDF_MAGIC = b"%PDF"


def verify_pdf(path: str, min_pages: int = 1, min_text_chars: int = 1500) -> dict:
    """Verify a downloaded file is a real, text-bearing scientific PDF.

    Returns dict(ok, pages, text_chars, reason).
    """
    result = {"ok": False, "pages": 0, "text_chars": 0, "reason": ""}
    if not os.path.exists(path):
        result["reason"] = "file missing"
        return result
    size = os.path.getsize(path)
    if size < 20_000:
        result["reason"] = f"file too small ({size} bytes)"
        return result
    with open(path, "rb") as fh:
        head = fh.read(1024)
    if _PDF_MAGIC not in head:
        # drained HTML / login / error page saved with a .pdf name
        low = head.lower()
        for marker, why in (
            (b"<html", "HTML page instead of PDF"),
            (b"captcha", "captcha / bot-check page"),
            (b"cf-error", "CDN error page"),
            (b"access denied", "access denied page"),
            (b"sign in", "login page"),
        ):
            if marker in low:
                result["reason"] = why
                return result
        result["reason"] = "not a PDF (bad magic bytes)"
        return result
    try:
        from pypdf import PdfReader

        reader = PdfReader(path, strict=False)
        pages = len(reader.pages)
        result["pages"] = pages
        if pages < min_pages:
            result["reason"] = f"only {pages} page(s)"
            return result
        chars = 0
        for page in reader.pages[: min(pages, 8)]:
            try:
                chars += len((page.extract_text() or "").strip())
            except Exception:
                continue
        result["text_chars"] = chars
        if chars < min_text_chars:
            result["reason"] = f"almost no extractable text ({chars} chars) - likely scan"
            return result
        result["ok"] = True
        result["reason"] = "ok"
        return result
    except Exception as exc:  # noqa: BLE001
        result["reason"] = f"parse error: {exc}"
        return result


# ----------------------------------------------------- geoscience relevance
# Substring lexicon: enough to recognise a genuine Earth-science full text.
GEO_LEXICON = (
    "geolog", "geophys", "geochem", "geoscience", "earth science", "subsurface",
    "crust", "mantle", "lithospher", "tecton", "fault", "fracture", "seismic",
    "earthquake", "microseismic", "borehole", "wellbore", "drilling", "reservoir",
    "permeability", "porosity", "petrophys", "hydrogeolog", "groundwater", "aquifer",
    "geothermal", "sediment", "stratigraph", "litholog", "sandstone", "carbonate",
    "shale", "coal", "mineral", "ore deposit", "magma", "volcan", "igneous",
    "metamorph", "soil", "landslide", "rock mechanics", "rock mass", "outcrop",
    "fluvial", "glacial", "permafrost", "karst", "hydrolog", "petroleum", "oilfield",
    "natural gas", "coalbed", "methane", "craton", "orogen", "rift", "subduction",
    "geodesy", "insar", "geomechanic", "proppant", "injection well", "production well",
    "shale gas", "tight reservoir", "geohazard", "unconformity", "basin", "hydraulic fracturing",
    "carbon storage", "co2 storage", "geological storage", "stimulation", "fractured",
)

# Word-boundary markers of other disciplines (guards against word-collision hits).
NON_GEO_PATTERNS = (
    r"\bpatient", r"\bclinical\b", r"\bcancer\b", r"\btumou?r\b", r"\bdental\b",
    r"\bglycation\b", r"\bin vitro\b", r"\bmice\b", r"\brat model\b",
    r"\bsupply chain\b", r"\btourism\b", r"\bclassroom\b", r"\bquestionnaire\b",
    r"\bcovid", r"\bvaccine\b", r"\bnursing\b", r"\bmarketing\b",
    r"\bsilicon carbide\b", r"\bultra-precision\b", r"\bgrinding\b",
    r"\bwafer\b", r"\bsemiconductor\b", r"\bceramic",
)

GEO_VENUE_PATTERNS = (
    "geo", "earth", "seismolog", "tectonic", "hydrogeolog", "rock mechanics",
    "petroleum", "geothermal", "solid earth", "basin research", "water resources",
    "mineral", "soil", "ocean", "lithos", "geotechnical", "natural resources",
)

GEO_FIELDS = {"geology", "geophysics", "environmental science", "geography",
              "earth science", "oceanography", "atmospheric science", "hydrology"}


def geo_relevance(text: str, venue: str = "", fields=(), threshold: int = 3) -> dict:
    """Classify a paper as geoscience / review / non-geoscience.

    ``geoscience`` needs real Earth-science vocabulary plus at least one of a
    matching venue or discipline field; a handful of colliding words (e.g.
    "subsurface fracture" in a materials-science paper) lands in ``review``.
    """
    low = (text or "").lower()
    hits = sorted({g for g in GEO_LEXICON if g in low})
    flags = sorted({m for m in NON_GEO_PATTERNS if re.search(m, low)})
    fset = {str(f).strip().lower() for f in (fields or []) if f}
    venue_ok = any(p in (venue or "").lower() for p in GEO_VENUE_PATTERNS)
    field_ok = bool(fset & GEO_FIELDS)
    if not hits:
        label = "non-geoscience"
    elif len(hits) >= threshold or ((venue_ok or field_ok) and len(hits) >= 2):
        label = "geoscience"
    else:
        label = "review"
    score = len(hits) + (2 if venue_ok else 0) + (2 if field_ok else 0) - 2 * len(flags)
    return {"label": label, "geo_hits": hits, "geo_hit_count": len(hits),
            "non_geo_flags": flags, "venue_match": venue_ok, "field_match": field_ok,
            "score": score}


def validate_search_terms(terms) -> list:
    """Return a de-duplicated term list and enforce the accumulated cap."""
    seen, out = set(), []
    for t in terms:
        key = " ".join(str(t).lower().split())
        if key and key not in seen:
            seen.add(key)
            out.append(str(t).strip())
    if len(out) > MAX_SEARCH_TERMS:
        audit("1_terms", "cap_applied",
              f"Search terms trimmed from {len(out)} to {MAX_SEARCH_TERMS} "
              f"(hard cap of this skill).", requested=len(out), kept=MAX_SEARCH_TERMS)
        out = out[:MAX_SEARCH_TERMS]
    return out


def success_count(results: dict | None = None) -> int:
    results = results if results is not None else (load_json(RESULTS_FILE, {}) or {})
    return sum(1 for v in results.values() if v.get("status") == "成功")


def hard_stop_reached(results: dict | None = None) -> bool:
    """True once accumulated successes reach the hard cap 80 (stop immediately).

    Reaching the cap ends the whole flow at once, so literature/ never exceeds
    HARD_STOP_SUCCESSES papers.
    """
    return success_count(results) >= HARD_STOP_SUCCESSES


if __name__ == "__main__":
    import sys

    ensure_dirs()
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        print(json.dumps(verify_pdf(sys.argv[2]), ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps({"root": ROOT, "successes": success_count(),
                          "cap": HARD_STOP_SUCCESSES, "target": DEFAULT_TARGET,
                          "hard_stop": hard_stop_reached()}, ensure_ascii=False))
    else:
        print(__doc__)
