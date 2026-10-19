# -*- coding: utf-8 -*-
"""Rater scoring: output/labelled_<stem>.csv -> breakpoint/score_audit.json

Applies every rubric table and formula from the prompt contract, and derives
the collection-priority label + suffixes. Nothing here may be memory-based;
all thresholds come from references/prompt-contract.md.
"""
import argparse, csv, glob, json, os

LEVEL = {"长期观测与业务运行数据中心":100, "权威领域汇聚型数据仓库":95, "领域科研数据出版仓库/共享平台":90, "成果级地球数据库/数据集":80, "综合级公共数据仓库/共享平台":75}
REGION = {"国家级":100, "大洲级":90, "全球级":85, "地区级":70}
# 研究区域重分类：官方 locations 标准值 -> 四档；无标准值时填实际区域名
REGION_TIERS = ("国家级", "大洲级", "全球级", "地区级")
# 官方 locations 无标准值时的常见实际区域名 -> 四档；可用 breakpoint/region_map.json 覆盖或补充
REGION_DEFAULT = {"美国": "国家级", "北美": "大洲级", "全球": "全球级", "全球海洋": "全球级"}
REGION_KEYWORDS = (("全球", "全球级"), ("公海", "大洲级"), ("北极", "大洲级"), ("南极", "大洲级"), ("极地", "大洲级"))
UNMAPPED_REGION = []

def load_region_map(root):
    p = os.path.join(root, "breakpoint", "region_map.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

def region_of(loc, extra):
    loc = str(loc).strip()
    if loc in REGION_TIERS:
        return loc
    if loc in extra:
        return extra[loc]
    if loc in REGION_DEFAULT:
        return REGION_DEFAULT[loc]
    for k, v in REGION_KEYWORDS:
        if k in loc:
            return v
    UNMAPPED_REGION.append(loc)
    return "国家级"
DIM  = {"四维":90, "三维":85, "二维":80, "一维":75, "零维":70, "未知":70}
TCOV = {"50年以上":100, "20-50年":95, "10-20年":90, "5-10年":85, "2-5年":80, "静态":75, "未知":75}
PROC = {"L0":100, "L1":90, "L2":80, "L3":70, "L4":60}

def cite(v):
    n = int(float(str(v).strip()))
    if n >= 10000: return "超强影响力", 100
    if n >= 5000:  return "强影响力", 90
    if n >= 1000:  return "较强影响力", 80
    if n >= 500:   return "较弱影响力", 70
    if n >= 100:   return "弱影响力", 60
    return "极弱影响力", 50

def plat(b):
    ps = [x.strip() for x in str(b).split(",") if x.strip()]
    if any(x in ("空基平台", "陆基平台", "水基平台") for x in ps): return "高敏感观测级", 100
    if any(x == "天基平台" for x in ps): return "中敏感遥感级", 85
    return "低敏感数据级", 70

def inst(cat, cls):
    cs = [x.strip() for x in str(cat).split(",") if x.strip()]
    cl = [x.strip() for x in str(cls).split(",") if x.strip()]
    best = 70
    if any(c in ("地球遥感仪器", "太阳/太空观测仪器") for c in cs): best = max(best, 85)
    if any(c == "原位/实验室仪器" for c in cs):
        nd = [c for c in cl if c != "数据分析"]
        best = max(best, 100 if (nd or not cl) else 70)
    return {100:"高敏感观测级", 85:"中敏感遥感级", 70:"低敏感数据级"}[best], best

def proc(p):
    b = 0
    for t in str(p).split(","):
        t = t.strip()
        if t[:2] in PROC: b = max(b, PROC[t[:2]])
    return b or 70

def dv_tier(v):   # 数据价值分级：>
    return "Tier0" if v > 90 else "Tier1" if v > 85 else "Tier2" if v > 80 else "Tier3" if v > 75 else "Tier4"
def ge_tier(v, a, b, c, d):   # 不可替代性/敏感性分级：>=
    return "Tier0" if v >= a else "Tier1" if v >= b else "Tier2" if v >= c else "Tier3" if v >= d else "Tier4"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    OUT = os.path.join(root, "output")
    cands = [f for f in glob.glob(os.path.join(OUT, "labelled_*.csv")) if not f.endswith("_score.csv")]
    if len(cands) != 1:
        raise SystemExit("expected exactly one labelled_*.csv, found %d" % len(cands))
    rows = list(csv.DictReader(open(cands[0], encoding="utf-8-sig")))
    region_map = load_region_map(root)
    res = []
    for r in rows:
        ls = LEVEL[r["数据库级别"]]; cl, cs = cite(r["被引数量"]); tc = TCOV[r["时间覆盖"]]; dm = DIM[r["数据维度"]]
        val = 0.4 * ls + 0.4 * cs + 0.1 * tc + 0.1 * dm
        reg = region_of(r["研究区域"], region_map); rs = REGION[reg]
        pl, ps = plat(r["平台-基座"]); il, isc = inst(r["仪器-大类"], r["仪器-中类"]); pr = proc(r["加工等级"])
        sens = 0.3 * rs + 0.2 * ps + 0.2 * isc + 0.3 * pr
        dims = [r["时间唯一性"], r["场地唯一性"], r["替代源稀缺度"]]
        irr = min(60 + 15 * sum(d == "I0" for d in dims) + 5 * sum(d == "I1" for d in dims), 100)
        tu, su = r["时间唯一性"], r["场地唯一性"]
        H = {"P0": [], "P1": [], "P2": [], "P3": []}
        if sens >= 95: H["P0"].append("S")
        if tu == "I0" and su == "I0": H["P0"].append("U")
        if sens >= 90: H["P1"].append("S")
        if tu == "I0" or su == "I0": H["P1"].append("U")
        if sens >= 85: H["P2"].append("S")
        if tu == "I1" and su == "I1": H["P2"].append("U")
        if val >= 90: H["P2"].append("V")
        if sens >= 80: H["P3"].append("S")
        if tu == "I1" or su == "I1": H["P3"].append("U")
        if val >= 80: H["P3"].append("V")
        lvl = next((L for L in ["P0", "P1", "P2", "P3"] if H[L]), None)
        if lvl:
            suf = [x for x in ["S", "U", "V"] if x in H[lvl]]
            prio, sfx = lvl, lvl + "-" + "".join(suf)
        else:
            prio, sfx = "P4", ""
        res.append(dict(r, **{
            "数据库级别评分": ls, "被引数量标签": cl, "被引数量评分": cs, "时间覆盖评分": tc, "数据维度评分": dm,
            "数据价值总分": round(val, 1), "研究区域重分类": reg, "研究区域评分": rs,
            "获取方式（平台）": pl, "获取方式（平台）评分": ps, "获取方式（仪器）": il, "获取方式（仪器）评分": isc,
            "加工等级评分": pr, "敏感性总分": round(sens, 1), "不可替代性总分": irr,
            "平均总分": round((val + sens + irr) / 3, 2), "采集优先级标签": prio, "次级标签": sfx,
            "数据价值分级": dv_tier(val), "不可替代性分级": ge_tier(irr, 90, 85, 80, 75), "敏感性分级": ge_tier(sens, 95, 90, 85, 80)}))
    if UNMAPPED_REGION:
        print("WARN 未映射研究区域(默认按国家级计)，可在 breakpoint/region_map.json 指定:", sorted(set(UNMAPPED_REGION)))
    json.dump(res, open(os.path.join(root, "breakpoint", "score_audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for x in res:
        print("%-40s val=%5.1f sens=%5.1f irr=%3d avg=%5.2f %s %-7s %s" % (
            x["数据库/数据集/数据名称"][:40], x["数据价值总分"], x["敏感性总分"], x["不可替代性总分"],
            x["平均总分"], x["采集优先级标签"], x["次级标签"], x["数据价值分级"]))

if __name__ == "__main__":
    main()
