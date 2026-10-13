"""Turn the raw browser harvest into deduped, enriched candidates.

Reads ``breakpoint/harvest_raw.json`` (written by the browser harvest step) and
writes ``breakpoint/candidates.json`` with citation counts, full journal names,
DOIs, authors and the openAccessPdf link resolved through the Semantic Scholar
``paper/batch`` endpoint - one request per 100 papers, with polite sleeps.

Usage:  python enrich_candidates.py
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import requests
from litlib import (BREAKPOINT_DIR, audit, load_json, save_json, validate_search_terms)

RAW = os.path.join(BREAKPOINT_DIR, "harvest_raw.json")
CAND = os.path.join(BREAKPOINT_DIR, "candidates.json")

harvest = load_json(RAW, {}) or {}
if not harvest:
    raise SystemExit("no harvest_raw.json - run the browser harvest step first")

kept = validate_search_terms(list(harvest.keys()))
harvest = {k: harvest[k] for k in kept}

# dedupe within each search term
per_term = {}
for term, rows in harvest.items():
    seen, keep = set(), []
    for r in rows:
        pid = r.get("paper_id") or ""
        if not pid or pid in seen:
            continue
        seen.add(pid)
        keep.append(r)
    per_term[term] = keep

total_rows = sum(len(v) for v in per_term.values())
audit("2_harvest", "harvest_summary",
      f"Harvested {len(per_term)} search terms, {total_rows} unique-per-term candidates. "
      f"Terms returning 0 rows were blocked by Semantic Scholar human verification.",
      per_term_counts={k: len(v) for k, v in per_term.items()})

# collect unique papers across all terms
papers = {}
for term, rows in per_term.items():
    for r in rows:
        pid = r["paper_id"]
        if pid not in papers:
            r2 = dict(r)
            r2["search_terms"] = [term]
            papers[pid] = r2
        else:
            papers[pid]["search_terms"].append(term)

ids = sorted(papers.keys())
audit("2_harvest", "unique_papers", f"{len(ids)} unique papers across all terms", count=len(ids))

FIELDS = "title,year,citationCount,venue,externalIds,openAccessPdf,authors,publicationTypes,isOpenAccess,openAccessPdf"
url = "https://api.semanticscholar.org/graph/v1/paper/batch"
enriched = {}
CH = 100
for i in range(0, len(ids), CH):
    chunk = ids[i:i + CH]
    for attempt in (1, 2, 3):
        try:
            r = requests.post(url, params={"fields": FIELDS}, json={"ids": chunk},
                              headers={"User-Agent": "LiteratureDownloader/1.0 (research; polite)"},
                              timeout=90)
            if r.status_code == 200:
                data = r.json()
                for rec in data:
                    if rec and rec.get("paperId"):
                        enriched[rec["paperId"]] = rec
                print(f"chunk {i//CH+1}: {len(data)} records (HTTP 200)")
                break
            print(f"chunk {i//CH+1} HTTP {r.status_code}; retry in 20s")
            time.sleep(20)
        except Exception as e:
            print(f"chunk {i//CH+1} error {e}; retry in 20s")
            time.sleep(20)
    if i + CH < len(ids):
        time.sleep(8)

audit("2_harvest", "batch_enrich",
      f"Enriched {len(enriched)}/{len(ids)} papers with citationCount/DOI/openAccessPdf "
      f"via paper/batch ({len(range(0, len(ids), CH))} requests).",
      enriched=len(enriched), requested=len(ids))

candidates = []
for pid in ids:
    r = papers[pid]
    e = enriched.get(pid, {})
    ext = e.get("externalIds") or {}
    oap = e.get("openAccessPdf") or {}
    authors = [a.get("name", "") for a in (e.get("authors") or [])]
    hv = (r.get("venue") or "").strip()
    hf = (r.get("fields") or "").strip()
    if hv and hf and hv.lower() == hf.lower():
        hv = ""
    if hv and "," in hv and len(hv.split(",")) <= 3 and all(len(x.split()) <= 2 for x in hv.split(",")):
        hv = ""
    cand = {
        "paper_id": pid,
        "title": e.get("title") or r.get("title", ""),
        "year": e.get("year") or r.get("year", ""),
        "citations": e.get("citationCount", ""),
        "venue": e.get("venue") or hv,
        "doi": ext.get("DOI", "") or (r.get("publisher_url", "") or "").replace("https://doi.org/", ""),
        "authors": authors or r.get("authors", []),
        "pdf_url": r.get("pdf_url", ""),
        "oa_pdf_url": oap.get("url", ""),
        "reader_url": r.get("reader_url", "") or f"https://www.semanticscholar.org/reader/{pid}",
        "publisher_url": r.get("publisher_url", ""),
        "paper_url": r.get("paper_url", ""),
        "search_term": r.get("search_terms", [""])[0],
        "search_terms": r.get("search_terms", []),
        "source_db": "Semantic Scholar",
        "publication_types": e.get("publicationTypes") or [],
        "fields_of_study": r.get("fields", ""),
    }
    candidates.append(cand)

save_json(CAND, candidates)
with_oap = sum(1 for c in candidates if c["oa_pdf_url"])
with_card_pdf = sum(1 for c in candidates if c["pdf_url"])
years = sorted({str(c["year"]) for c in candidates if c["year"]})
audit("2_harvest", "candidates_built",
      f"{len(candidates)} candidates; {with_card_pdf} with a PDF link on the result card, "
      f"{with_oap} with an openAccessPdf from the API. Year range seen: {years[0]}-{years[-1]}.",
      candidates=len(candidates), card_pdf=with_card_pdf, api_oa=with_oap, years=years)
print(json.dumps({"candidates": len(candidates), "card_pdf": with_card_pdf,
                  "api_oa": with_oap, "years": years}, ensure_ascii=False))
