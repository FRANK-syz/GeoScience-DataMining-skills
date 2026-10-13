"""Final hygiene for literature/: discipline exclusions, strict validation,
de-duplication, version de-duplication and contiguous renumbering.

Reads optional ``breakpoint/exclusions.json``::

    {
      "non_geo_dois":      {"10.xxxx/yyy": "why this is not Earth science"},
      "reject_prefixes":   ["016_advanced glycation", "..."]
    }

Populate it while reviewing the relevance audit so every removal is auditable.
Updates download_results.json so the inventory CSV and the folder stay in sync.

Usage:  python finalize_literature.py
"""
from __future__ import annotations

import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from litlib import (  # noqa: E402
    BREAKPOINT_DIR,
    EXCLUSIONS_FILE,
    LITERATURE_DIR,
    RESULTS_FILE,
    audit,
    load_json,
    save_json,
    verify_pdf,
)

from pypdf import PdfReader  # noqa: E402

THESIS = ("theses service", "phd thesis", "doctoral thesis", "dissertation",
          "a thesis submitted", "thesis submitted for")
COVER = ("open access (oa) strat", "stratégie de l'université", "sample cover image",
         "cover image for this issue", "this is a cover sheet", "front cover")
SI = ("supporting information", "supplementary material", "reviewer comment",
      "author response to reviewers", "reviewer report")
PREPRINT = re.compile(r"-(19|20)\d{2}-\d+$|egusphere|^10\.5194/[a-z]{2,4}-(19|20)\d{2}-\d+", re.I)


def stem(fname: str) -> str:
    return re.sub(r"^\d{3}_", "", os.path.splitext(fname)[0])


def drop(fname: str, why: str, results: dict) -> None:
    path = os.path.join(LITERATURE_DIR, fname)
    if os.path.exists(path):
        os.remove(path)
    for v in results.values():
        if v.get("file") == fname:
            v["status"] = "页面不符合要求"
            v["note"] = why
            v["file"] = ""


def main() -> int:
    results = load_json(RESULTS_FILE, {}) or {}
    excl = load_json(EXCLUSIONS_FILE, {}) or {}
    removed, dupes, version_dupes = [], [], []

    # 1. discipline exclusions -------------------------------------------------
    for k, why in (excl.get("non_geo_dois") or {}).items():
        fname = (results.get(k.lower()) or {}).get("file")
        if fname:
            removed.append((fname, "non-geoscience: " + why))
            drop(fname, "non-geoscience full text removed: " + why, results)
    for prefix in (excl.get("reject_prefixes") or []):
        for f in sorted(os.listdir(LITERATURE_DIR)):
            if f.startswith(prefix):
                removed.append((f, "listed in exclusions.json"))
                drop(f, "removed via exclusions.json", results)

    # 2. strict validation ----------------------------------------------------
    for f in sorted(os.listdir(LITERATURE_DIR)):
        if not f.lower().endswith(".pdf"):
            continue
        try:
            r = PdfReader(os.path.join(LITERATURE_DIR, f), strict=False)
            n = len(r.pages)
            first = re.sub(r"\s+", " ", (r.pages[0].extract_text() or "")).lower()
            total = sum(len(re.sub(r"\s+", " ", (p.extract_text() or ""))) for p in r.pages[:12])
        except Exception as exc:  # noqa: BLE001
            removed.append((f, f"unreadable: {exc}"))
            drop(f, f"unreadable PDF: {exc}", results)
            continue
        why = ""
        if any(k in first for k in THESIS):
            why = "thesis/dissertation excluded"
        elif any(k in first for k in COVER) and (n <= 3 or total < 6000):
            why = "publisher cover sheet or OA notice only"
        elif any(k in first for k in SI) and n <= 4:
            why = "supporting information / reviewer material"
        elif n <= 1 and total < 4000:
            why = "single page without body text (abstract-like)"
        if why:
            removed.append((f, why))
            drop(f, why, results)

    # 3. exact duplicate titles ----------------------------------------------
    groups = {}
    for f in sorted(os.listdir(LITERATURE_DIR)):
        if f.lower().endswith(".pdf"):
            groups.setdefault(stem(f), []).append(f)
    for s, fs in groups.items():
        for extra in sorted(fs)[1:]:
            dupes.append(extra)
            drop(extra, f"duplicate of {sorted(fs)[0]}", results)

    # 4. near-duplicate titles -> keep the published version ------------------
    bydoi = {v.get("file"): v.get("doi", "") for v in results.values() if v.get("file")}
    files = sorted(f for f in os.listdir(LITERATURE_DIR) if f.lower().endswith(".pdf"))
    for i in range(len(files)):
        for j in range(i + 1, len(files)):
            a, b = files[i], files[j]
            if not os.path.exists(os.path.join(LITERATURE_DIR, a)) or \
               not os.path.exists(os.path.join(LITERATURE_DIR, b)):
                continue
            if difflib.SequenceMatcher(None, stem(a), stem(b)).ratio() <= 0.93:
                continue
            da, db = bydoi.get(a, ""), bydoi.get(b, "")
            loser = a if (PREPRINT.search(da) and not PREPRINT.search(db)) else (
                b if (PREPRINT.search(db) and not PREPRINT.search(da)) else None)
            if loser:
                version_dupes.append(loser)
                drop(loser, "duplicate version removed; published version retained", results)

    # 5. renumber contiguously -----------------------------------------------
    files = sorted(os.listdir(LITERATURE_DIR))
    files = [f for f in files if f.lower().endswith(".pdf")]
    files.sort(key=stem)
    tmp = []
    for f in files:
        t = os.path.join(LITERATURE_DIR, "_tmp_" + f)
        os.rename(os.path.join(LITERATURE_DIR, f), t)
        tmp.append((t, stem(f)))
    mapping = {}
    for i, (t, s) in enumerate(tmp, start=1):
        new = f"{i:03d}_{s}.pdf"
        dest = os.path.join(LITERATURE_DIR, new)
        while os.path.exists(dest):
            new = f"{i:03d}_{s}-dup.pdf"
            dest = os.path.join(LITERATURE_DIR, new)
        os.rename(t, dest)
        mapping[s] = new
    for v in results.values():
        if v.get("status") == "成功" and v.get("file"):
            s = stem(v["file"])
            if s in mapping:
                v["file"] = mapping[s]

    save_json(RESULTS_FILE, results)
    ok = sum(1 for v in results.values() if v.get("status") == "成功")
    files_now = sorted(f for f in os.listdir(LITERATURE_DIR) if f.lower().endswith(".pdf"))
    tracked = {v["file"] for v in results.values() if v.get("status") == "成功" and v.get("file")}
    audit("6_finalize", "literature_finalized",
          f"excluded {len(removed)}, {len(dupes)} duplicates, {len(version_dupes)} duplicate versions; "
          f"{len(files_now)} files remain; success records {ok}; orphans "
          f"{sorted(set(files_now) - tracked)}.",
          excluded=removed, duplicates=dupes, version_duplicates=version_dupes,
          files=len(files_now), success_records=ok, orphans=sorted(set(files_now) - tracked))
    print({"excluded": len(removed), "duplicates": len(dupes), "version_duplicates": len(version_dupes),
           "files": len(files_now), "success_records": ok, "match": len(files_now) == len(tracked)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
