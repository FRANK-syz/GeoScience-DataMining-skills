"""Final gate: cross-check the inventory against the files and re-verify usability.

Guards the three boundary requirements of this skill:

1. the counts agree - ``literature/`` files == inventory rows == success records
   (and the success count never exceeds the cap of 80);
2. every inventory row resolves to a real file on disk, and every file is
   claimed by exactly one inventory row;
3. every file is actually usable - it opens, parses, has >= 1 page with
   extractable body text (not a scan, not an abstract/login/error page).

Writes ``output/verification_report.md`` plus ``breakpoint/verification_report.json``
and exits non-zero when anything does not match, so a mismatch can never pass
silently.

Usage:
  python verify_deliverables.py [--min-pages 1] [--min-chars 1500]
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from litlib import (  # noqa: E402
    BREAKPOINT_DIR,
    DEFAULT_TARGET,
    HARD_STOP_SUCCESSES,
    INVENTORY_CSV,
    LITERATURE_DIR,
    RESULTS_FILE,
    SEARCH_INFO_CSV,
    audit,
    load_json,
    sanitize_filename,
    save_json,
    verify_pdf,
)


def stem_of(fname: str) -> str:
    return re.sub(r"^\d{3}_", "", os.path.splitext(fname)[0])


def read_csv_rows(path: str) -> list:
    if not os.path.exists(path):
        return []
    with io.open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-pages", type=int, default=1)
    ap.add_argument("--min-chars", type=int, default=1500)
    args = ap.parse_args()

    files = sorted(f for f in os.listdir(LITERATURE_DIR) if f.lower().endswith(".pdf")) \
        if os.path.isdir(LITERATURE_DIR) else []
    stems = {stem_of(f): f for f in files}

    inventory = read_csv_rows(INVENTORY_CSV)
    search_rows = read_csv_rows(SEARCH_INFO_CSV)
    results = load_json(RESULTS_FILE, {}) or {}
    success = {k: v for k, v in results.items() if v.get("status") == "成功"}

    problems = []

    # (1) counts must agree
    counts = {"files_on_disk": len(files), "inventory_rows": len(inventory),
              "success_records": len(success), "search_info_rows": len(search_rows)}
    if len(files) != len(inventory):
        problems.append(f"count mismatch: {len(files)} files on disk vs {len(inventory)} inventory rows")
    if len(files) != len(success):
        problems.append(f"count mismatch: {len(files)} files on disk vs {len(success)} success records")
    if len(files) > HARD_STOP_SUCCESSES:
        problems.append(f"boundary breached: {len(files)} files exceed the cap of {HARD_STOP_SUCCESSES}")

    # (2) every inventory row must resolve to a file, and every file must be claimed
    claimed = {}
    missing = []
    for row in inventory:
        title = (row.get("文章标题") or "").strip()
        if not title:
            problems.append("inventory row without a title")
            continue
        want = os.path.splitext(sanitize_filename(0, title))[0][4:]
        if want in stems:
            claimed.setdefault(want, 0)
            claimed[want] += 1
        else:
            missing.append(title)
    if missing:
        problems.append(f"{len(missing)} inventory rows have no matching file in literature/")
    unclaimed = sorted(set(stems) - set(claimed))
    if unclaimed:
        problems.append(f"{len(unclaimed)} files are not listed in the inventory")
    duplicated = {s: n for s, n in claimed.items() if n > 1}
    if duplicated:
        problems.append(f"{len(duplicated)} files are claimed by more than one inventory row")

    # (3) every file must be usable
    unusable = []
    for f in files:
        check = verify_pdf(os.path.join(LITERATURE_DIR, f),
                           min_pages=args.min_pages, min_text_chars=args.min_chars)
        if not check["ok"]:
            unusable.append({"file": f, "reason": check["reason"]})
    if unusable:
        problems.append(f"{len(unusable)} files are not usable full texts")

    report = {"counts": counts, "cap": HARD_STOP_SUCCESSES, "target": DEFAULT_TARGET,
              "missing_inventory_rows": missing, "unclaimed_files": unclaimed,
              "duplicate_claims": duplicated, "unusable_files": unusable,
              "problems": problems, "match": not problems}
    save_json(os.path.join(BREAKPOINT_DIR, "verification_report.json"), report)

    lines = ["# 交付复核报告", "",
             "## 数量一致性",
             f"- `literature/` PDF 文件数：{counts['files_on_disk']}",
             f"- 清单 `literature_download_inventory.csv` 记录数：{counts['inventory_rows']}",
             f"- 成功记录数（download_results.json）：{counts['success_records']}",
             f"- 检索明细 `literature_search_info.csv` 记录数：{counts['search_info_rows']}",
             f"- 成功上限：{HARD_STOP_SUCCESSES}（是否突破：{'是' if counts['files_on_disk'] > HARD_STOP_SUCCESSES else '否'}）",
             f"- 目标数量：{DEFAULT_TARGET}（是否达成：{'是' if counts['files_on_disk'] >= DEFAULT_TARGET else '否'}）",
             "",
             "## 逐条对应",
             f"- 清单中找不到对应文件的条目：{len(missing)}",
             f"- 未被清单收录的文件：{len(unclaimed)}",
             f"- 被多条记录重复认领的文件：{len(duplicated)}",
             "",
             "## 可用性复核",
             f"- 逐篇重新打开/解析并抽取正文文本，不通过：{len(unusable)} 篇",
             ]
    for it in unusable[:50]:
        lines.append(f"  - {it['file']}：{it['reason']}")
    for it in missing[:50]:
        lines.append(f"  - 缺文件：{it}")
    for it in unclaimed[:50]:
        lines.append(f"  - 多余文件：{it}")
    lines += ["", "## 结论",
              "全部一致，清单数量无误。" if not problems else
              "**存在不一致，需处理后再交付。**"]
    for pb in problems:
        lines.append(f"- {pb}")

    os.makedirs(os.path.dirname(INVENTORY_CSV), exist_ok=True)
    with io.open(os.path.join(os.path.dirname(INVENTORY_CSV), "verification_report.md"),
                 "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    audit("8_verify", "deliverables_verified",
          f"files={counts['files_on_disk']} inventory={counts['inventory_rows']} "
          f"records={counts['success_records']} usable={len(files) - len(unusable)} "
          f"problems={len(problems)}",
          **report)
    print(json.dumps({"match": report["match"], "problems": problems,
                      **counts}, ensure_ascii=False))
    return 0 if report["match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
