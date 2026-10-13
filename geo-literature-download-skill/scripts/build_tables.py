"""Build the two deliverable tables from the resumable breakpoint data.

  output/literature_search_info.csv        - every browsed entry, one row per
                                             (paper, search term), any outcome
  output/literature_download_inventory.csv - the successfully saved full texts
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from litlib import (BREAKPOINT_DIR, LITERATURE_DIR, OUTPUT_DIR, audit, load_json)

CANDIDATES = os.path.join(BREAKPOINT_DIR, "candidates.json")
RESULTS = os.path.join(BREAKPOINT_DIR, "download_results.json")
SEARCH_CSV = os.path.join(OUTPUT_DIR, "literature_search_info.csv")
INV_CSV = os.path.join(OUTPUT_DIR, "literature_download_inventory.csv")

SEARCH_FIELDS = ["文章标题", "发表年份", "被引数", "期刊名全称", "DOI",
                 "原文pdf下载地址", "是否下载成功", "检索词", "来源文献数据库"]
INV_FIELDS = ["文章标题", "作者（前三位）", "发表年份", "被引数", "期刊名全称",
              "DOI", "原文pdf下载地址", "来源检索式", "来源文献数据库"]
DISCIPLINES = {
    "Engineering", "Geology", "Environmental Science", "Physics", "Biology", "Geography",
    "Materials Science", "Computer Science", "Medicine", "Chemistry", "Mathematics",
    "Economics", "Psychology", "Sociology", "Business", "Political Science", "Art",
    "History", "Philosophy", "Geophysics", "Agricultural and Food Sciences", "Education",
    "Law", "Linguistics", "Statistics", "Astronomy",
}

VALID = ["成功", "人机验证/访问限制", "页面不符合要求", "出版商链接不开放", "链接失效", "其他失败原因"]


def norm(raw: str) -> str:
    return raw if raw in VALID else "其他失败原因"


def main() -> int:
    cands = load_json(CANDIDATES, []) or []
    results = load_json(RESULTS, {}) or {}

    def lookup(c):
        for k in ((c.get("doi") or "").lower(), c.get("paper_id") or "", c.get("title") or ""):
            if k and k in results:
                return results[k]
        return None

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rows, seen = [], set()
    for c in cands:
        terms = c.get("search_terms") or [c.get("search_term", "")]
        r = lookup(c)
        for t in terms:
            key = ((c.get("doi") or "").lower() or c.get("paper_id") or c.get("title", ""), t)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "文章标题": c.get("title", ""),
                "发表年份": str(c.get("year", "") or ""),
                "被引数": str(c.get("citations", "") or ""),
                "期刊名全称": c.get("venue", ""),
                "DOI": c.get("doi", ""),
                "原文pdf下载地址": c.get("pdf_url") or c.get("oa_pdf_url", ""),
                "是否下载成功": norm(r.get("status", "")) if r else "",
                "检索词": t,
                "来源文献数据库": c.get("source_db", "Semantic Scholar"),
            })

    rows.sort(key=lambda x: (x["检索词"], x["发表年份"] or ""))
    with open(SEARCH_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SEARCH_FIELDS)
        w.writeheader()
        w.writerows(rows)

    # canonical metadata from the enriched candidate set (venue/citations/authors)
    meta = {}
    for c in cands:
        for k in ((c.get("doi") or "").lower(), c.get("paper_id") or ""):
            if k:
                meta[k] = c

    inv = []
    for r in results.values():
        if r.get("status") != "成功":
            continue
        c = meta.get((r.get("doi") or "").lower()) or {}
        r = dict(r)
        v = c.get("venue") or ""
        if not v:
            cur = (r.get("venue") or "").strip()
            parts = [q.strip() for q in cur.split(",") if q.strip()]
            if len(parts) >= 2 and len(parts) <= 4 and all(q in DISCIPLINES for q in parts):
                cur = ""
            v = cur
        r["venue"] = v
        if r.get("citations") in ("", None) and c.get("citations") not in ("", None):
            r["citations"] = c.get("citations")
        if not r.get("authors") and c.get("authors"):
            r["authors"] = c["authors"]
        authors = r.get("authors") or []
        if authors and isinstance(authors[0], dict):
            authors = [a.get("name", "") for a in authors]
        inv.append({
            "文章标题": r.get("title", ""),
            "作者（前三位）": "; ".join(authors[:3]),
            "发表年份": str(r.get("year", "") or ""),
            "被引数": str(r.get("citations", "") or ""),
            "期刊名全称": r.get("venue", ""),
            "DOI": r.get("doi", ""),
            "原文pdf下载地址": r.get("pdf_url", ""),
            "来源检索式": r.get("search_term", ""),
            "来源文献数据库": r.get("source_db", "Semantic Scholar"),
        })
    inv.sort(key=lambda x: (x["来源检索式"], x["发表年份"] or ""))
    with open(INV_CSV, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=INV_FIELDS)
        w.writeheader()
        w.writerows(inv)

    files = [f for f in os.listdir(LITERATURE_DIR) if f.lower().endswith(".pdf")]
    tracked = {r.get("file") for r in results.values() if r.get("status") == "成功" and r.get("file")}
    summary = {
        "browsed_rows": len(rows),
        "success_records": len(inv),
        "pdf_files_on_disk": len(files),
        "match": len(tracked) == len(files) and len(inv) == len(files),
        "orphan_files": sorted(set(files) - tracked),
    }
    audit("tables", "rebuilt",
          f"search_info rows={len(rows)} (browsed entries), inventory={len(inv)}, "
          f"files={len(files)}, matched={summary['match']}", **summary)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
