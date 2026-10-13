"""Screen every downloaded full text for Earth-science relevance.

For each `success` record with a file in ``literature/`` the first pages are read
and scored against the geoscience lexicon in ``litlib.geo_relevance()`` (venue
and discipline tags from ``candidates.json`` are used as extra evidence).

Outputs
-------
- ``breakpoint/relevance_audit.json`` : per-paper verdict (auditable)
- ``output/relevance_report.md``      : human-readable summary
- ``breakpoint/exclusions.json``      : with ``--apply``, confident
  ``non-geoscience`` DOIs are merged into ``non_geo_dois`` so
  ``finalize_literature.py`` removes them from ``literature/``.

Nothing is deleted here: removals stay explicit and auditable.

Usage:
  python audit_relevance.py                # report only
  python audit_relevance.py --apply        # also queue confident non-geoscience for removal
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from litlib import (  # noqa: E402
    BREAKPOINT_DIR,
    CANDIDATES_FILE,
    EXCLUSIONS_FILE,
    LITERATURE_DIR,
    OUTPUT_DIR,
    RESULTS_FILE,
    audit,
    geo_relevance,
    load_json,
    save_json,
)

from pypdf import PdfReader  # noqa: E402


def first_pages_text(path: str, pages: int = 3) -> str:
    try:
        reader = PdfReader(path, strict=False)
    except Exception:  # noqa: BLE001
        return ""
    text = []
    for page in reader.pages[:pages]:
        try:
            text.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    return re.sub(r"\s+", " ", " ".join(text))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="merge confident non-geoscience DOIs into exclusions.json")
    ap.add_argument("--threshold", type=int, default=3,
                    help="distinct geoscience terms needed for a confident match")
    args = ap.parse_args()

    results = load_json(RESULTS_FILE, {}) or {}
    candidates = load_json(CANDIDATES_FILE, []) or []
    meta = {}
    for c in candidates:
        for k in ((c.get("doi") or "").lower(), c.get("paper_id") or ""):
            if k:
                meta[k] = c

    verdicts, counts = {}, {"geoscience": 0, "review": 0, "non-geoscience": 0}
    for key, rec in results.items():
        if rec.get("status") != "成功" or not rec.get("file"):
            continue
        path = os.path.join(LITERATURE_DIR, rec["file"])
        if not os.path.exists(path):
            continue
        cand = meta.get((rec.get("doi") or "").lower()) or {}
        fields = cand.get("fields_of_study") or []
        if isinstance(fields, str):
            fields = [f.strip() for f in fields.split(",") if f.strip()]
        venue = cand.get("venue") or rec.get("venue") or ""
        text = first_pages_text(path) + " " + (rec.get("title") or "")
        verdict = geo_relevance(text, venue=venue, fields=fields, threshold=args.threshold)
        verdict.update({"title": rec.get("title", ""), "doi": rec.get("doi", ""),
                        "venue": venue, "file": rec["file"],
                        "search_term": rec.get("search_term", "")})
        verdicts[key] = verdict
        counts[verdict["label"]] += 1

    save_json(os.path.join(BREAKPOINT_DIR, "relevance_audit.json"), verdicts)

    review = [(k, v) for k, v in verdicts.items() if v["label"] != "geoscience"]
    review.sort(key=lambda kv: kv[1]["geo_hit_count"])

    lines = ["# 地球科学相关性复核", "",
             f"- 复核全文数：{len(verdicts)}",
             f"- 判定为地球科学：{counts['geoscience']}",
             f"- 需人工确认：{counts['review']}",
             f"- 判定为非地球科学：{counts['non-geoscience']}",
             "", "## 判定标准",
             "- 正文含 >= {t} 个地球科学术语，或含 >= 2 个术语且期刊/学科字段命中地球科学 -> 地球科学".format(t=args.threshold),
             "- 仅有少量词面重合（如材料学里的 subsurface/fracture）-> 需人工确认",
             "- 无任何地球科学术语，或命中其他学科标记 -> 非地球科学（需剔除）",
             "", "## 需人工确认/剔除的条目", ""]
    if not review:
        lines.append("（无）")
    for k, v in review:
        lines += [f"### {v['label']} | {v['title'][:90]}",
                  f"- DOI: {v['doi'] or '-'}",
                  f"- 期刊: {v['venue'] or '-'}",
                  f"- 文件: {v['file']}",
                  f"- 地球科学术语命中 {v['geo_hit_count']}：{', '.join(v['geo_hits'][:8]) or '无'}",
                  f"- 其他学科标记：{', '.join(v['non_geo_flags']) or '无'}",
                  ""]
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with io.open(os.path.join(OUTPUT_DIR, "relevance_report.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    applied = []
    if args.apply:
        excl = load_json(EXCLUSIONS_FILE, {}) or {}
        nongeo = excl.setdefault("non_geo_dois", {})
        for k, v in verdicts.items():
            if v["label"] == "non-geoscience" and v["doi"] and v["doi"] not in nongeo:
                nongeo[v["doi"]] = "auto: no geoscience vocabulary in the full text"
                applied.append(v["doi"])
        save_json(EXCLUSIONS_FILE, excl)

    audit("5_relevance", "relevance_audited",
          f"Relevance audit: {counts['geoscience']} geoscience, {counts['review']} to review, "
          f"{counts['non-geoscience']} non-geoscience"
          + (f"; {len(applied)} queued for removal." if args.apply else "."),
          counts=counts, threshold=args.threshold, applied=applied,
          review_dois=[v["doi"] for _, v in review])
    print(json.dumps({"checked": len(verdicts), **counts,
                      "queued_for_removal": len(applied)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
