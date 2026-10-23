# -*- coding: utf-8 -*-
"""Superviser checks -> breakpoint/superviser_audit.json

Implements the mechanical checks from the prompt contract (GCMD compliance,
blank big-class fields, separator, recomputation, concentration, structure).
Evidence-based checks (entry reachability, citation provenance, funding text)
must be done by the agent and reported in Warning.md.
"""
import argparse, csv, glob, json, os
from collections import Counter

LEVEL = {"长期观测与业务运行数据中心":100, "权威领域汇聚型数据仓库":95, "领域科研数据出版仓库/共享平台":90, "成果级地球数据库/数据集":80, "综合级公共数据仓库/共享平台":75}
REG = {"国家级":100, "大洲级":90, "全球级":85, "地区级":70}
TCM = {"50年以上":100, "20-50年":95, "10-20年":90, "5-10年":85, "2-5年":80, "静态":75, "未知":75}
DM  = {"四维":90, "三维":85, "二维":80, "一维":75, "零维":70, "未知":70}
PR  = {"L0":100, "L1":90, "L2":80, "L3":70, "L4":60}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    OUT = os.path.join(root, "output")
    bp = json.load(open(os.path.join(root, "breakpoint", "taxonomy_bundle.json"), encoding="utf-8"))
    def zh(vals): return set(str(v).strip() for v in vals if v)
    TOPICS = zh([r["topic_zh"] for r in bp["sciencekeywords"]]); TERMS = zh([r["term_zh"] for r in bp["sciencekeywords"]])
    BASIS = zh([r["basis_zh"] for r in bp["platforms"]]);   PCAT = zh([r["category_zh"] for r in bp["platforms"]])
    ICAT = zh([r["category_zh"] for r in bp["instruments"]]); ICLS = zh([r["class_zh"] for r in bp["instruments"]])
    ITYP = zh([r["type_zh"] for r in bp["instruments"]])
    lab = list(csv.DictReader(open([f for f in glob.glob(os.path.join(OUT, "labelled_*.csv")) if not f.endswith("_score.csv")][0], encoding="utf-8-sig")))
    sc = list(csv.DictReader(open([f for f in glob.glob(os.path.join(OUT, "labelled_*_score.csv"))][0], encoding="utf-8-sig")))
    # 综合数据门户条目不参与打标/打分（prompt-contract §3 特例）：监管检查对其跳过
    normal_lab = [r for r in lab if r["数据库级别"] != "综合数据门户"]
    normal_sc = [r for r in sc if r["数据库级别"] != "综合数据门户"]
    portal_rows = [r["数据库/数据集/数据名称"] for r in lab if r["数据库级别"] == "综合数据门户"]
    if portal_rows:
        print("综合数据门户(跳过评分/合规检查):", portal_rows)
    issues = []
    def chk(f, allowed, ax=True):
        for r in lab:
            for t in [x.strip() for x in r[f].split(",") if x.strip()]:
                if t == "综合" and ax: continue
                if t not in allowed: issues.append((r["数据库/数据集/数据名称"], f, t))
    chk("地球科学领域-领域", TOPICS); chk("地球科学领域-专题", TERMS)
    chk("平台-基座", BASIS, False); chk("平台-大类", PCAT)
    chk("仪器-大类", ICAT, False); chk("仪器-中类", ICLS); chk("仪器-小类", ITYP)
    print("GCMD越界:", issues)
    empty = [(r["数据库/数据集/数据名称"], f) for r in normal_lab for f in ["地球科学领域-领域", "平台-基座", "仪器-大类"] if not r[f].strip()]
    print("大类留空:", empty)
    bad = [(r["数据库/数据集/数据名称"], f) for r in lab for f in
           ["地球科学领域-领域","地球科学领域-专题","平台-基座","平台-大类","仪器-大类","仪器-中类","仪器-小类"]
           if "," in r[f] and ", " not in r[f]]
    print("分隔符异常:", bad)
    valid = {"国家级","大洲级","全球级","地区级"}
    rc = sorted(set(r["研究区域"] for r in normal_sc if r["研究区域"].strip()))
    print("研究区域取值:", rc, "| 合规:", set(rc) <= valid)
    print("研究区域原值分布:", Counter(r["研究区域"] for r in normal_lab if r["研究区域"].strip()))
    print("被引空白:", [r["数据库/数据集/数据名称"] for r in normal_lab if not str(r["被引数量"]).strip()])
    low = [(r["数据库/数据集/数据名称"], r["被引数量"]) for r in lab if str(r["被引数量"]).strip().isdigit() and int(r["被引数量"]) < 100]
    print("被引<100:", len(low))
    fund = [(r["数据库/数据集/数据名称"], r["资助来源"], r["资助国家"]) for r in lab]
    print("资助不一致:", [f for f in fund if (f[1].strip() == "") != (f[2].strip() == "")], "| 无资助:", [f[0] for f in fund if f[1].strip() == ""])
    diff = []
    for r in normal_sc:
        n = int(float(r["被引数量"]))
        cs = 100 if n >= 10000 else 90 if n >= 5000 else 80 if n >= 1000 else 70 if n >= 500 else 60 if n >= 100 else 50
        val = 0.4 * LEVEL[r["数据库级别"]] + 0.4 * cs + 0.1 * TCM[r["时间覆盖"]] + 0.1 * DM[r["数据维度"]]
        sens = 0.3 * REG[r["研究区域"]] + 0.2 * int(r["获取方式（平台）评分"]) + 0.2 * int(r["获取方式（仪器）评分"]) + 0.3 * int(r["加工等级评分"])
        dims = [r["时间唯一性"], r["场地唯一性"], r["替代源稀缺度"]]
        irr = min(60 + 15 * sum(d == "I0" for d in dims) + 5 * sum(d == "I1" for d in dims), 100)
        avg = round((val + sens + irr) / 3, 2)
        pmax = max([PR[t.strip()[:2]] for t in r["加工等级"].split(",") if t.strip()[:2] in PR])
        if (abs(val - float(r["数据价值总分"])) > 0.05 or abs(sens - float(r["敏感性总分"])) > 0.05
                or irr != int(r["不可替代性总分"]) or abs(avg - float(r["平均总分"])) > 0.01
                or pmax != int(r["加工等级评分"])):
            diff.append(r["数据库/数据集/数据名称"])
    print("复算不一致:", diff)
    cols = ["数据库级别评分","被引数量评分","时间覆盖评分","数据维度评分","研究区域评分","获取方式（平台）评分",
            "获取方式（仪器）评分","加工等级评分","数据价值总分","敏感性总分","不可替代性总分","平均总分"]
    conc = {}
    for c in cols:
        cnt = Counter(str(x[c]) for x in normal_sc if str(x[c]).strip()); m2, c2 = cnt.most_common(1)[0]; conc[c] = (m2, c2, round(100 * c2 / len(normal_sc), 1))
    for c, (m2, c2, p) in conc.items():
        print("  %-16s %s %d/%d=%.1f%%%s" % (c, m2, c2, len(normal_sc), p, "  <==>75%" if p > 75 else ""))
    hdr = list(lab[0].keys()); dup = [k for k, v in Counter(hdr).items() if v > 1]
    allempty = [k for k in hdr if all((r[k] or "").strip() == "" for r in lab)]
    print("列数:", len(hdr), "| 重复列名:", dup, "| 整列为空:", allempty)
    json.dump({"issues": issues, "rc": rc, "diff": diff, "conc": conc, "dup": dup, "allempty": allempty,
               "low_citation": low, "blank": empty, "sep_bad": bad, "no_funding": [f[0] for f in fund if f[1].strip() == ""]},
              open(os.path.join(root, "breakpoint", "superviser_audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
