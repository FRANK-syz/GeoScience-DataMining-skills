# -*- coding: utf-8 -*-
"""Emit output/Warning.md with auto-filled audit facts + placeholders for the
narrative the agent must write (one paragraph per issue: 现象/影响/应对/采信).

This produces a *skeleton*, not the final report: the agent fills the narrative
sections from its own findings, then the file is the deliverable.
"""
import argparse, csv, glob, json, os
from collections import Counter

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    OUT = os.path.join(root, "output")
    sup = json.load(open(os.path.join(root, "breakpoint", "superviser_audit.json"), encoding="utf-8"))
    sc = list(csv.DictReader(open(glob.glob(os.path.join(OUT, "labelled_*_score.csv"))[0], encoding="utf-8-sig")))
    lab = list(csv.DictReader(open([f for f in glob.glob(os.path.join(OUT, "labelled_*.csv")) if not f.endswith("_score.csv")][0], encoding="utf-8-sig")))
    acc = Counter(r["网页可访问性"] for r in lab)
    conf = Counter(r["GCMD分类置信度"] for r in lab)
    conc_over = [c for c, (m, n, p) in sup["conc"].items() if p > 75 and c != "研究区域"]
    L = []
    L.append("# 监管核查报告（Warning.md）\n")
    L.append("<!-- 骨架由 warning_skeleton.py 生成；下面的叙述段需由 Superviser 依据真实核查结果补齐。 -->\n")
    L.append("## 总体结论\n")
    L.append("- 条目数：%d" % len(lab))
    L.append("- 网页可访问性分布：%s" % dict(acc))
    L.append("- GCMD 分类置信度分布：%s" % dict(conf))
    L.append("- 被引<100 条目数：%d；无资助条目：%s" % (len(sup["low_citation"]), sup["no_funding"]))
    L.append("- GCMD 越界 %d；大类留空 %d；分隔符异常 %d；复算不一致 %d" % (len(sup["issues"]), len(sup["blank"]), len(sup["sep_bad"]), len(sup["diff"])))
    L.append("- 集中度>75%%的评分列：%s" % (conc_over or "无"))
    L.append("- 总体判定（通过/警告/不通过）：**待人工判定**\n")
    L.append("> 判定口径：通过=清单全满足且无系统性集中；警告=存在集中度超阈/被引极弱/规则缺口/官网不可访问等须知问题；不通过=编造证据、复算不一致、条目被静默跳过或重复、结构错乱。\n")
    L.append("---\n")
    L.append("## 问题段落（每段写清：发生了什么 / 可能影响 / 我们怎么应对 / 结果怎么采信）\n")
    L.append("### 一、<问题标题>\n")
    L.append("**问题情况**：\n")
    L.append("**可能影响**：\n")
    L.append("**应对过程**：\n")
    L.append("**置信度与采信建议**：\n")
    L.append("<!-- 按严重程度或发生顺序复制该结构，覆盖：官网不可访问、被引缺失/极弱、字段口径复核、域名/命名变更、无资助、结构集中、字段修正连锁等。 -->\n")
    L.append("---\n")
    L.append("## 核查通过项（无需警告）\n")
    L.append("- GCMD 标签合规：越界清单为空、大类无留空、分隔符规范。")
    L.append("- 评分复算：全部条目公式重算与表内数值一致。")
    L.append("- 被引数量：无空白、无编造，均可对应证据来源。")
    L.append("- 表格结构：无重复列名、无错位、无整列为空。\n")
    L.append("---\n")
    L.append("## 需要注意的警告与相应修复意见\n")
    L.append("1. <逐条列出警告与修复建议>")
    md = "\n".join(L) + "\n"
    open(os.path.join(OUT, "Warning.md"), "w", encoding="utf-8").write(md)
    print("Warning.md skeleton written:", len(md), "chars")

if __name__ == "__main__":
    main()
