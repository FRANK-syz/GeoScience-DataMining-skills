# -*- coding: utf-8 -*-
"""breakpoint/score_audit.json -> output/labelled_<stem>_score.csv + output/Quick_report.csv"""
import argparse, csv, glob, json, os

# (输出列名, score_audit 中的键)
SC = [("数据库/数据集/数据名称","数据库/数据集/数据名称"),("数据库或数据门户名称","数据库或数据门户名称"),
 ("数据库官网网址入口","数据库官网网址入口"),("数据库下载网址入口","数据库下载网址入口"),
 ("地球科学领域","地球科学领域-领域"),("所属国家与地区","所属国家与地区"),
 ("平均总分","平均总分"),("数据价值总分","数据价值总分"),("不可替代性总分","不可替代性总分"),("敏感性总分","敏感性总分"),
 ("数据库级别","数据库级别"),("数据库级别评分","数据库级别评分"),("时间覆盖","时间覆盖"),("时间覆盖评分","时间覆盖评分"),
 ("数据维度","数据维度"),("数据维度评分","数据维度评分"),("被引数量","被引数量"),("被引数量评分","被引数量评分"),
 ("时间唯一性","时间唯一性"),("场地唯一性","场地唯一性"),("替代源稀缺度","替代源稀缺度"),
 ("研究区域","研究区域重分类"),("研究区域评分","研究区域评分"),
 ("获取方式（平台）","获取方式（平台）"),("获取方式（平台）评分","获取方式（平台）评分"),
 ("获取方式（仪器）","获取方式（仪器）"),("获取方式（仪器）评分","获取方式（仪器）评分"),
 ("加工等级","加工等级"),("加工等级评分","加工等级评分"),
 ("资助来源","资助来源"),("资助国家","资助国家"),("数据获取条件","数据获取条件"),("网页可访问性","网页可访问性")]

Q = [("数据库/数据集/数据名称","数据库/数据集/数据名称"),("数据库或数据门户名称","数据库或数据门户名称"),
 ("数据库官网网址入口","数据库官网网址入口"),("数据库下载网址入口","数据库下载网址入口"),
 ("地球科学领域","地球科学领域-领域"),("所属国家与地区","所属国家与地区"),
 ("采集优先级标签","采集优先级标签"),("次级标签","次级标签"),("平均总分","平均总分"),
 ("数据价值分数","数据价值总分"),("不可替代性分数","不可替代性总分"),("敏感性分数","敏感性总分"),
 ("数据价值分级","数据价值分级"),("不可替代性分级","不可替代性分级"),("敏感性分级","敏感性分级"),
 ("资助来源","资助来源"),("资助国家","资助国家"),("数据获取条件","数据获取条件"),("网页可访问性","网页可访问性")]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    OUT = os.path.join(root, "output")
    res = json.load(open(os.path.join(root, "breakpoint", "score_audit.json"), encoding="utf-8"))
    cands = [f for f in glob.glob(os.path.join(OUT, "labelled_*.csv")) if not f.endswith("_score.csv")]
    stem = os.path.basename(cands[0])[len("labelled_"):-len(".csv")]
    with open(os.path.join(OUT, "labelled_" + stem + "_score.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow([h for h, _ in SC])
        for x in res: w.writerow([x[k] for _, k in SC])
    with open(os.path.join(OUT, "Quick_report.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow([h for h, _ in Q])
        for x in res: w.writerow([x[k] for _, k in Q])
    print("wrote labelled_%s_score.csv (%d cols) + Quick_report.csv (%d cols)" % (stem, len(SC), len(Q)))

if __name__ == "__main__":
    main()
