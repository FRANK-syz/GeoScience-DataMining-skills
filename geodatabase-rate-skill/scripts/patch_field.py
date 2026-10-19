# -*- coding: utf-8 -*-
"""Patch one field of one record in breakpoint/labelled_batch_all.json.

The JSON is the single source of truth; never hand-edit an output CSV.
After patching, rerun the pipeline (see SKILL.md) so every output is regenerated.

Examples
--------
python patch_field.py --root . --name "USGS NWIS (National Water Information System)" \
    --field site_uniqueness --value I0 --note "场地唯一性按地下观测口径更正为I0（与EDX/GDR一致）"
python patch_field.py --root . --name "AmeriFlux" --field access --value 注册公开
"""
import argparse, json, os

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--name", required=True, help="record name (exact, or a unique prefix)")
    ap.add_argument("--field", required=True)
    ap.add_argument("--value", required=True, help="JSON literal; bare strings are accepted")
    ap.add_argument("--note", default="", help="text appended to the row's notes")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    p = os.path.join(root, "breakpoint", "labelled_batch_all.json")
    R = json.load(open(p, encoding="utf-8"))
    hits = [r for r in R if r["name"] == a.name] or [r for r in R if r["name"].startswith(a.name)]
    if len(hits) != 1:
        raise SystemExit("expected exactly one match for %r, got %d" % (a.name, len(hits)))
    r = hits[0]
    try:
        val = json.loads(a.value)
    except Exception:
        val = a.value
    before = r.get(a.field)
    r[a.field] = val
    if a.note:
        r["notes"] = (r.get("notes", "") + "；" + a.note) if r.get("notes") else a.note
    json.dump(R, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("%s: %s  %r -> %r" % (r["name"], a.field, before, val))
    print("Now rerun: labeller_compile -> score -> write_reports -> verify -> warning_skeleton -> make_audit")

if __name__ == "__main__":
    main()
