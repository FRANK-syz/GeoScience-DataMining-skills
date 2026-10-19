# -*- coding: utf-8 -*-
"""Write breakpoint/audit.json: the end-to-end audit trail (stages, inputs,
outputs, file list, and any post-review field updates recorded in
breakpoint/post_review_updates.json)."""
import argparse, datetime, glob, json, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    BP, OUT = os.path.join(root, "breakpoint"), os.path.join(root, "output")
    def js(p, d=None):
        p = os.path.join(BP, p)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d
    lab = js("labelled_batch_all.json", [])
    labfiles = sorted(glob.glob(os.path.join(BP, "labelled_batch_*.json")))
    recs = []
    for f in labfiles: recs += json.load(open(f, encoding="utf-8"))
    score = js("score_audit.json", [])
    sup = js("superviser_audit.json", {})
    upd = js("post_review_updates.json", [])
    audit = {
        "run_finished": datetime.datetime.now().isoformat(timespec="seconds"),
        "input_records": len(recs),
        "taxonomy_source": ["地球科学分类.xlsx", "地球科学分类-zh.xlsx (GCMD)"],
        "steps": [
            {"agent": "Labeller", "stage": "分类打标",
             "outputs": ["output/labelled_<原文件名>.csv", "output/label_statistic.csv"], "records": len(recs)},
            {"agent": "Rater", "stage": "价值评分",
             "outputs": ["output/labelled_<原文件名>_score.csv", "output/Quick_report.csv"], "records": len(score)},
            {"agent": "Superviser", "stage": "监管核查", "outputs": ["output/Warning.md"],
             "gcmd_out_of_range": len(sup.get("issues", [])), "recompute_mismatch": len(sup.get("diff", []))},
        ],
        "post_review_updates": upd,
        "files": [os.path.relpath(p, root) for p in sorted(glob.glob(os.path.join(OUT, "*")))],
    }
    json.dump(audit, open(os.path.join(BP, "audit.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("audit.json written; outputs:", audit["files"])

if __name__ == "__main__":
    main()
