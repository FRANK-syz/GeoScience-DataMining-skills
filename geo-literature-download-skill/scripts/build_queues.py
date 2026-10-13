"""Split enriched candidates into a direct-download queue and a browser queue.

- ``breakpoint/script_queue.json``  : hosts that answer plain HTTP requests
  (Semantic Scholar hosted PDFs first, then other direct PDF links)
- ``breakpoint/browser_queue.json`` : publishers behind JS bot challenges
  (MDPI, Springer, Wiley, ScienceDirect, Nature, OUP, ...), each annotated with a
  direct landing URL derived from the PDF link so the browser can skip doi.org

Usage:  python build_queues.py [papers_per_term]   (default 20)
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from litlib import (  # noqa: E402
    BREAKPOINT_DIR,
    BROWSER_QUEUE_FILE,
    CANDIDATES_FILE,
    QUEUE_FILE,
    RESULTS_FILE,
    audit,
    load_json,
    save_json,
)

# Publishers that front their PDFs with a JavaScript bot check.
JS_WALL = ("mdpi.com", "springer.com", "wiley.com", "sciencedirect.com", "nature.com",
           "oup.com", "hindawi.com", "tandfonline.com", "sagepub.com", "iop.org",
           "iopscience", "copernicus.org", "asme.org", "onepetro.org", "geoscienceworld.org",
           "degruyter.com", "cambridge.org", "acs.org", "rsc.org")
# Of those, the ones that reliably work once the browser has solved the challenge.
RELIABLE = ("mdpi.com", "springer.com", "frontiersin.org", "copernicus.org", "nature.com",
            "hindawi.com", "oup.com", "tandfonline.com", "sagepub.com", "cambridge.org",
            "degruyter.com")


def direct_score(c: dict) -> int:
    u = c.get("pdf_url") or ""
    if not u or any(h in u for h in JS_WALL):
        return 0
    if "pdfs.semanticscholar.org" in u:
        return 3
    if u.lower().endswith(".pdf") or "/pdf" in u.lower():
        return 2
    if "/download/" in u.lower():
        return 2
    return 1


def derive_landing(pdf_url: str, doi: str) -> str:
    """A publisher landing URL that avoids the doi.org redirect chain."""
    u = pdf_url or ""
    if "mdpi.com" in u:
        return re.sub(r"/pdf(\?.*)?$", "", u)
    if "link.springer.com" in u and "/content/pdf/" in u:
        return "https://link.springer.com/article/" + doi if doi else ""
    if "frontiersin.org" in u:
        return re.sub(r"/pdf(\?.*)?$", "", u)
    if "copernicus.org" in u:
        return re.sub(r"\.pdf$", ".html", u)
    if "hindawi.com" in u:
        return re.sub(r"/pdf$", "/", u)
    if "nature.com" in u:
        return re.sub(r"\.pdf$", "", u)
    if "academic.oup.com" in u:
        return re.sub(r"/pdf.*$", "", u)
    return ""


def key_of(c: dict) -> str:
    return (c.get("doi") or "").lower() or c.get("paper_id") or c.get("title", "")


def main() -> int:
    per_term = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    cands = load_json(CANDIDATES_FILE, []) or []
    results = load_json(RESULTS_FILE, {}) or {}
    if not cands:
        raise SystemExit("no candidates.json - run enrich_candidates.py first")

    direct_by_term, browser_items, seen = {}, [], set()
    for c in cands:
        k = key_of(c)
        if (results.get(k) or {}).get("status") == "成功" or k in seen:
            continue
        seen.add(k)
        if direct_score(c) > 0:
            direct_by_term.setdefault(c.get("search_term", ""), []).append(c)
            continue
        landing = c.get("publisher_url") or (("https://doi.org/" + c["doi"]) if c.get("doi") else "")
        pdf = c.get("pdf_url") or c.get("oa_pdf_url") or ""
        if not landing.startswith("http"):
            continue
        browser_items.append({
            "title": c["title"], "year": c.get("year", ""), "citations": c.get("citations", ""),
            "venue": c.get("venue", ""), "doi": c.get("doi", ""), "authors": c.get("authors", []),
            "search_term": c.get("search_term", ""), "source_db": c.get("source_db", "Semantic Scholar"),
            "paper_id": c.get("paper_id"), "landing": landing, "landing2": derive_landing(pdf, c.get("doi", "")),
            "pdf_url": pdf, "round": 1,
        })

    for t in direct_by_term:
        direct_by_term[t].sort(key=lambda c: (direct_score(c), int(c.get("citations") or 0)), reverse=True)

    script_q, seen2 = [], set()
    terms = [t for t in direct_by_term if direct_by_term[t]]
    for i in range(per_term):
        for t in terms:
            lst = direct_by_term[t]
            if i >= len(lst):
                continue
            c = lst[i]
            k = key_of(c)
            if k in seen2:
                continue
            seen2.add(k)
            script_q.append({
                "title": c["title"], "year": c.get("year", ""), "citations": c.get("citations", ""),
                "venue": c.get("venue", ""), "doi": c.get("doi", ""), "authors": c.get("authors", []),
                "search_term": t, "source_db": c.get("source_db", "Semantic Scholar"),
                "paper_id": c.get("paper_id"), "url": c.get("pdf_url") or c.get("oa_pdf_url"),
                "alt_urls": [u for u in (c.get("oa_pdf_url"), c.get("reader_url"))
                             if u and u != c.get("pdf_url")],
                "round": 1,
            })

    browser_items.sort(key=lambda x: (0 if any(h in (x["pdf_url"] + x["landing"]) for h in RELIABLE) else 1,
                                      -int(x.get("citations") or 0)))
    save_json(QUEUE_FILE, script_q)
    save_json(BROWSER_QUEUE_FILE, browser_items)
    audit("3_queue", "queues_built",
          f"{per_term} per term: {len(script_q)} direct-channel papers and "
          f"{len(browser_items)} JS-walled publisher papers queued.",
          per_term=per_term, direct=len(script_q), browser=len(browser_items))
    print({"script_queue": len(script_q), "browser_queue": len(browser_items)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
