"""Write the per-round report and the final report.

Usage:
  python make_reports.py --round 1     # output/round1_report.md
  python make_reports.py --final       # output/Literature_Downloader_final_report.md
                                       # + output/manual_download_needed.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from litlib import (  # noqa: E402
    CANDIDATES_FILE,
    DEFAULT_TARGET,
    HARD_STOP_SUCCESSES,
    HARVEST_FILE,
    LITERATURE_DIR,
    MAX_SEARCH_TERMS,
    OUTPUT_DIR,
    RESULTS_FILE,
    SEARCH_TERMS_FILE,
    audit,
    load_json,
)

STATUS_ORDER = ["成功", "人机验证/访问限制", "页面不符合要求", "出版商链接不开放", "链接失效", "其他失败原因"]


def gather() -> dict:
    results = load_json(RESULTS_FILE, {}) or {}
    verification = load_json(os.path.join(os.path.dirname(RESULTS_FILE), "verification_report.json"), {}) or {}
    relevance = load_json(os.path.join(os.path.dirname(RESULTS_FILE), "relevance_audit.json"), {}) or {}
    cands = load_json(CANDIDATES_FILE, []) or []
    harvest = load_json(HARVEST_FILE, {}) or {}
    terms = [t["term"] for t in (load_json(SEARCH_TERMS_FILE, {}) or {}).get("search_terms", [])]
    files = sorted(f for f in os.listdir(LITERATURE_DIR) if f.lower().endswith(".pdf")) \
        if os.path.isdir(LITERATURE_DIR) else []
    success = sum(1 for v in results.values() if v.get("status") == "成功")
    per_term = Counter(v.get("search_term", "") for v in results.values() if v.get("status") == "成功")
    cand_per_term = Counter(c.get("search_term", "") for c in cands)
    return {
        "results": results, "cands": cands, "harvest": harvest, "terms": terms, "files": files,
        "success": success, "attempted": len(results),
        "browsed": sum(len(v) for v in harvest.values()), "unique": len(cands),
        "per_term": per_term, "cand_per_term": cand_per_term,
        "statuses": Counter(v.get("status", "其他失败原因") for v in results.values()),
        "verification": verification, "relevance": relevance,
    }


def round_report(rnd: int) -> None:
    g = gather()
    rate = g["success"] / g["attempted"] * 100 if g["attempted"] else 0.0
    lines = [f"# geo-literature-download-skill 第 {rnd} 轮报告", "",
             f"- 浏览/检索的条目数（含跨检索词重复）：{g['browsed']}",
             f"- 去重后独立文献数：{g['unique']}",
             f"- 累计尝试下载条目数：{g['attempted']}",
             f"- 累计成功下载数量：{g['success']}",
             f"- 本轮/累计成功率：{rate:.1f}%（{g['success']}/{g['attempted']}）",
             f"- 是否达到目标（≥{DEFAULT_TARGET}）：{'是' if g['success'] >= DEFAULT_TARGET else '否'}",
             f"- 是否达到成功上限（{HARD_STOP_SUCCESSES} 篇即停止）：{'是' if g['success'] >= HARD_STOP_SUCCESSES else '否'}",
             "", "## 各检索词覆盖情况", "| 检索词 | 候选条目 | 成功下载 |", "| --- | --- | --- |"]
    for t in g["terms"]:
        lines.append(f"| {t} | {g['cand_per_term'].get(t, 0)} | {g['per_term'].get(t, 0)} |")
    lines += ["", "## 失败状态分布", "| 状态 | 数量 |", "| --- | --- |"]
    for k in STATUS_ORDER:
        if g["statuses"].get(k):
            lines.append(f"| {k} | {g['statuses'][k]} |")
    path = os.path.join(OUTPUT_DIR, f"round{rnd}_report.md")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    audit("7_report", "round_report_written", f"round {rnd} report written to {path}",
          round=rnd, successes=g["success"])


def final_report() -> None:
    g = gather()
    results = g["results"]
    rate = g["success"] / g["attempted"] * 100 if g["attempted"] else 0.0
    blocked = [(v.get("title", ""), v.get("pdf_url", ""), v.get("doi", ""))
               for v in results.values() if v.get("status") == "人机验证/访问限制"]
    n_nongeo = sum(1 for v in results.values() if "non-geoscience" in (v.get("note") or ""))
    n_thesis = sum(1 for v in results.values() if "thesis" in (v.get("note") or ""))
    n_cover = sum(1 for v in results.values() if "cover sheet" in (v.get("note") or ""))
    n_single = sum(1 for v in results.values() if "single page" in (v.get("note") or ""))
    n_dupe = sum(1 for v in results.values() if "duplicate" in (v.get("note") or ""))

    lines = ["# 下载文献阶段最终报告", "", "## 使用的所有检索词"]
    for i, t in enumerate(g["terms"], 1):
        lines.append(f"{i}. {t}")
    lines += [
        "",
        f"检索词总数：{len(g['terms'])}（本技能上限 {MAX_SEARCH_TERMS} 个）",
        "",
        "## 核心指标",
        f"- 检索的文献条目总数（含跨检索词重复）：{g['browsed']}",
        f"- 去重后独立文献数：{g['unique']}",
        f"- 尝试下载条目总数：{g['attempted']}",
        f"- 成功下载的文献条目总数：{g['success']}",
        f"- 下载成功率：{rate:.1f}%（{g['success']}/{g['attempted']}）",
        f"- 清单成功记录数 {g['success']} vs literature/ 实际文件数 {len(g['files'])} —— "
        f"{'完全匹配' if g['success'] == len(g['files']) else '不匹配'}",
        f"- 是否达成收集数量目标（≥{DEFAULT_TARGET}）：{'是，已达成' if g['success'] >= DEFAULT_TARGET else '否，未达成'}",
        f"- 是否达到成功上限（{HARD_STOP_SUCCESSES} 篇，达到即停止获取）：{'是' if g['success'] >= HARD_STOP_SUCCESSES else '否'}",
        "",
        "## 结果与排重",
        f"- 剔除非地球科学条目 {n_nongeo} 篇、学位论文 {n_thesis} 篇、出版商封面/OA 通知页 {n_cover} 篇、"
        f"单页无正文 {n_single} 篇、重复条目 {n_dupe} 篇。",
        "- 验证判据：HTTP 200 且非错误跳转、PDF 魔数、可解析文本（非纯扫描）、至少一页正文、正文文本量达标。",
        "- 去重：按 DOI 与标题去重，预印本与正式版保留正式版。",
        "",
        "## 复核（清单数量与领域）",
        f"- 清单数量复核：{'一致，无差异' if g['verification'].get('match') else '未通过或尚未运行 verify_deliverables.py'}",
        f"- 清单记录数 / 实际文件数 / 成功记录数："
        f"{(g['verification'].get('counts') or {}).get('inventory_rows', '-')} / "
        f"{(g['verification'].get('counts') or {}).get('files_on_disk', len(g['files']))} / "
        f"{(g['verification'].get('counts') or {}).get('success_records', g['success'])}",
        f"- 可用性复核：不通过 {(g['verification'].get('unusable_files') or []) and len(g['verification']['unusable_files']) or 0} 篇"
        + ("（未运行 verify_deliverables.py）" if not g['verification'] else ""),
        ("- 地球科学相关性复核："
         + "，".join(f"{k} {v}" for k, v in sorted(
             Counter(v.get('label', '') for v in g['relevance'].values()).items()))
         + f"（需人工确认 {sum(1 for v in g['relevance'].values() if v.get('label') == 'review')} 篇）")
        if g['relevance'] else "- 地球科学相关性复核：未运行 audit_relevance.py",
        "",
        "## 交付文件",
        f"- `literature/`：{len(g['files'])} 篇通过全文验证的开放获取 PDF（命名 NNN_标题.pdf）",
        "- `output/literature_search_info.csv`：检索过的全部条目",
        "- `output/literature_download_inventory.csv`：成功下载清单",
        "- `output/manual_download_needed.md`：人机验证/访问限制链接清单",
        "- `breakpoint/`：中间数据与审计记录（audit_log.jsonl 可断点重启）",
        "- `scripts/`：本次使用的全部脚本",
        "",
        "## 过程说明",
        f"- 因出版商人机验证/访问限制未自动获取：{len(blocked)} 条。",
        f"- 各检索词成功下载数量：{json.dumps({t: g['per_term'].get(t, 0) for t in g['terms']}, ensure_ascii=False)}",
    ]
    if g["success"] < DEFAULT_TARGET:
        lines += ["", "## 未达成目标（需人工决策）",
                  "可选择：① 从头继续自动检索下载；② 用 OpenAlex/Unpaywall/PubMed 等开放获取来源补充；"
                  "③ 按 manual_download_needed.md 人工下载受限链接。"]
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "Literature_Downloader_final_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    manual = ["# 需人工下载的链接（人机验证/访问限制）", "", f"共 {len(blocked)} 条。", ""]
    for i, (t, u, d) in enumerate(blocked, 1):
        manual += [f"{i}. {t}", f"   - DOI: {d or '-'}", f"   - 链接: {u or '-'}"]
    with open(os.path.join(OUTPUT_DIR, "manual_download_needed.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(manual) + "\n")

    audit("7_report", "final_report_written",
          f"final report written: successes={g['success']}, files={len(g['files'])}, "
          f"target_met={g['success'] >= DEFAULT_TARGET}",
          successes=g["success"], files=len(g["files"]),
          target_met=g["success"] >= DEFAULT_TARGET)
    print(json.dumps({"success": g["success"], "attempted": g["attempted"],
                      "files": len(g["files"]), "target_met": g["success"] >= DEFAULT_TARGET,
                      "cap": HARD_STOP_SUCCESSES,
                      "hard_stop": g["success"] >= HARD_STOP_SUCCESSES,
                      "verified": bool(g["verification"].get("match"))}, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int)
    ap.add_argument("--final", action="store_true")
    args = ap.parse_args()
    if args.round:
        round_report(args.round)
    if args.final or not args.round:
        final_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
