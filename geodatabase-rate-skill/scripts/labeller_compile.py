# -*- coding: utf-8 -*-
"""Labeller compile: breakpoint/labelled_batch_*.json  ->  output/labelled_<stem>.csv + output/label_statistic.csv

Reads the row-level records the Labeller wrote (single source of truth) and
emits the 30-column labelled table with ZH GCMD labels, plus the
domain x platform x instrument co-occurrence statistic.
"""
import argparse, csv, glob, json, os
from collections import Counter

COLS = ["数据ID","数据库/数据集/数据名称","数据库或数据门户名称","数据库官网网址入口","数据库下载网址入口",
 "所属组织","所属国家与地区","数据库级别","地球科学领域-领域","地球科学领域-专题","平台-基座","平台-大类",
 "仪器-大类","仪器-中类","仪器-小类","研究区域","GCMD分类置信度","被引数量","高被引文献","时间覆盖","数据维度",
 "时间唯一性","场地唯一性","替代源稀缺度","加工等级","资助来源","资助国家","资助来源文本证据","数据获取条件","网页可访问性"]

def read_text(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "gb2312", "gb18030", "utf-8"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    raise SystemExit("cannot decode " + path)

def find_input(root):
    for f in sorted(os.listdir(root)):
        if f.lower().endswith(".csv") and not f.startswith("labelled_") and f not in ("Quick_report.csv", "label_statistic.csv"):
            return f
    raise SystemExit("no input CSV found in " + root)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    BP, OUT = os.path.join(root, "breakpoint"), os.path.join(root, "output")
    os.makedirs(OUT, exist_ok=True)
    bundle = json.load(open(os.path.join(BP, "taxonomy_bundle.json"), encoding="utf-8"))
    topic2zh = {r["topic"]: r["topic_zh"] for r in bundle["sciencekeywords"] if r["topic"]}
    term2zh  = {r["term"]: r["term_zh"] for r in bundle["sciencekeywords"] if r["term"]}
    basis2zh = {r["basis"]: r["basis_zh"] for r in bundle["platforms"]}
    pcat2zh  = {r["category"]: r["category_zh"] for r in bundle["platforms"] if r["category"]}
    icat2zh  = {r["category"]: r["category_zh"] for r in bundle["instruments"]}
    icls2zh  = {r["class"]: r["class_zh"] for r in bundle["instruments"] if r["class"]}
    ityp2zh  = {r["type"]: r["type_zh"] for r in bundle["instruments"] if r["type"]}

    def L(arr, mp):
        out = []
        for x in (arr or []):
            x = (x or "").strip()
            if not x:
                continue
            out.append("综合" if x == "综合" else mp.get(x, "!!" + x))
        return ", ".join(out)

    inp = find_input(root)
    stem = os.path.splitext(inp)[0]
    inrows = list(csv.DictReader(read_text(os.path.join(root, inp)).splitlines()))
    order = [r["数据名称"].strip() for r in inrows if r.get("数据名称", "").strip()]
    idbyname = {r["数据名称"].strip(): r.get("数据ID", "").strip() for r in inrows if r.get("数据名称", "").strip()}

    recs = []
    for fp in sorted(glob.glob(os.path.join(BP, "labelled_batch_*.json"))):
        recs += json.load(open(fp, encoding="utf-8"))
    byname = {d["name"].strip(): d for d in recs}

    rows = []
    for nm in order:
        d = byname[nm]
        rows.append({
         "数据ID": idbyname.get(nm, ""), "数据库/数据集/数据名称": d["name"], "数据库或数据门户名称": d.get("portal_name", ""),
         "数据库官网网址入口": d.get("home_url", ""), "数据库下载网址入口": d.get("download_url", ""),
         "所属组织": d.get("org", ""), "所属国家与地区": d.get("country", ""), "数据库级别": d.get("level", ""),
         "地球科学领域-领域": L(d.get("science_topic"), topic2zh), "地球科学领域-专题": L(d.get("science_term"), term2zh),
         "平台-基座": L(d.get("platform_basis"), basis2zh), "平台-大类": L(d.get("platform_category"), pcat2zh),
         "仪器-大类": L(d.get("instrument_category"), icat2zh), "仪器-中类": L(d.get("instrument_class"), icls2zh),
         "仪器-小类": L(d.get("instrument_type"), ityp2zh), "研究区域": d.get("location", ""),
         "GCMD分类置信度": d.get("gcmd_conf", ""), "被引数量": d.get("citations", ""), "高被引文献": d.get("cited_paper", ""),
         "时间覆盖": d.get("time_coverage", ""), "数据维度": d.get("data_dim", ""),
         "时间唯一性": d.get("time_uniqueness", ""), "场地唯一性": d.get("site_uniqueness", ""), "替代源稀缺度": d.get("rarity", ""),
         "加工等级": d.get("processing", ""), "资助来源": d.get("funding_source", ""), "资助国家": d.get("funding_country", ""),
         "资助来源文本证据": d.get("funding_evidence", ""), "数据获取条件": d.get("access", ""), "网页可访问性": d.get("accessibility", "")})

    out_csv = os.path.join(OUT, "labelled_" + stem + ".csv")
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)
    print("labelled rows", len(rows), "cols", len(COLS), "->", out_csv)

    def tags(r, fields):
        s = set()
        for f in fields:
            for t in [x.strip() for x in r[f].split(",") if x.strip()]:
                s.add(t)
        return s

    paircnt = Counter()
    for r in rows:
        sci  = tags(r, ["地球科学领域-领域", "地球科学领域-专题"])
        plat = tags(r, ["平台-基座", "平台-大类"])
        inst = tags(r, ["仪器-大类", "仪器-中类", "仪器-小类"])
        for label, A, B in [("地球科学领域×平台", sci, plat), ("地球科学领域×仪器", sci, inst), ("平台×仪器", plat, inst)]:
            for x in A:
                for y in B:
                    paircnt[(label, x, y)] += 1
    with open(os.path.join(OUT, "label_statistic.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["字段组合", "标签A", "标签B", "共现次数"])
        for (label, x, y), c in sorted(paircnt.items(), key=lambda kv: (-kv[1], kv[0])):
            w.writerow([label, x, y, c])
    print("co-occurrence rows", len(paircnt))

if __name__ == "__main__":
    main()
