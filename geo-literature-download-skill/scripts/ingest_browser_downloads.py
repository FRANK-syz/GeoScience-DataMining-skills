"""Move browser-downloaded PDFs into literature/ after full-text verification.

Idempotent: records `moved_to` so a later re-run can re-register an entry even
if another process rewrote download_results.json in the meantime.
"""
import json, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from litlib import (BREAKPOINT_DIR, LITERATURE_DIR, audit, load_json, sanitize_filename,
                    save_json, unique_path, verify_pdf)

BR = os.path.join(BREAKPOINT_DIR, "browser_results.json")
RESULTS = os.path.join(BREAKPOINT_DIR, "download_results.json")

br = load_json(BR, {}) or {}
results = load_json(RESULTS, {}) or {}

def stem_of(fname):
    return re.sub(r"^\d{3}_", "", os.path.splitext(fname)[0])

on_disk = {}
for f in os.listdir(LITERATURE_DIR):
    if f.lower().endswith(".pdf"):
        on_disk.setdefault(stem_of(f), f)

def next_index():
    n = 0
    for f in os.listdir(LITERATURE_DIR):
        if f[:3].isdigit():
            n = max(n, int(f[:3]))
    for v in results.values():
        f = v.get("file") or ""
        if f[:3].isdigit():
            n = max(n, int(f[:3]))
    return n + 1

def register(key, rec, path):
    check = verify_pdf(path)
    if not check["ok"]:
        rec["status"] = "页面不符合要求"
        rec["note"] = check["reason"]
        return False
    results[key] = {
        "title": rec["title"], "year": rec.get("year", ""), "citations": rec.get("citations", ""),
        "venue": rec.get("venue", ""), "doi": rec.get("doi", ""), "pdf_url": rec.get("pdf_url", ""),
        "search_term": rec.get("search_term", ""), "source_db": rec.get("source_db", "Semantic Scholar"),
        "authors": rec.get("authors", []), "status": "成功", "file": os.path.basename(path),
        "verified_pages": check["pages"], "verified_chars": check["text_chars"],
        "note": check["reason"], "channel": "browser:publisher", "round": 1,
    }
    return True

moved = rereg = failed = 0
idx = next_index()
for key, rec in br.items():
    if (results.get(key) or {}).get("status") == "成功":
        continue
    target = rec.get("moved_to")
    if target and os.path.exists(target):
        if register(key, rec, target):
            rec["status"] = "moved"; rereg += 1
        br[key] = rec
        continue
    p = rec.get("path")
    if p and os.path.exists(p):
        dest = unique_path(LITERATURE_DIR, sanitize_filename(idx, rec["title"]))
        shutil.move(p, dest)
        rec["moved_to"] = dest
        if register(key, rec, dest):
            rec["status"] = "moved"; moved += 1; idx += 1
        else:
            failed += 1
        br[key] = rec
        continue
    # file already moved by an earlier run: match by sanitized title stem
    want = os.path.splitext(sanitize_filename(0, rec["title"]))[0][4:]
    if want in on_disk:
        found = os.path.join(LITERATURE_DIR, on_disk[want])
        rec["moved_to"] = found
        if register(key, rec, found):
            rec["status"] = "moved"; rereg += 1
        br[key] = rec

save_json(BR, br)
save_json(RESULTS, results)
ok = sum(1 for v in results.values() if v.get("status") == "成功")
files = len([f for f in os.listdir(LITERATURE_DIR) if f.lower().endswith(".pdf")])
audit("3_round1", "ingest_browser",
      f"Browser ingest: {moved} new moves, {rereg} re-registered, {failed} rejected.",
      moved=moved, reregistered=rereg, rejected=failed)
print(json.dumps({"moved": moved, "reregistered": rereg, "rejected": failed,
                  "success_records": ok, "files_on_disk": files}))
