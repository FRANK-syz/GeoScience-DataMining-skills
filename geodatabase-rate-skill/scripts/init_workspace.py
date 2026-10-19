#!/usr/bin/env python3
"""geodatabase-rate-skill：建立工作区目录与审计骨架。

用法： python init_workspace.py [工作目录]
重复执行安全：已存在的文件不会被覆盖。
"""
import datetime, json, os, sys

AGENTS = ["Labeller", "Rater", "Superviser"]

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台中文输出


def main():
    root = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()
    for d in ("scripts", "output", "breakpoint", "literature"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    ledger = os.path.join(root, "breakpoint", "audit_log.json")
    if not os.path.exists(ledger):
        json.dump({
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "workspace": root,
            "schema": {"agent": "Labeller|Rater|Superviser", "step": "int",
                       "action": "该步做了什么", "evidence": "URL/文件/命令", "result": "产出或结论",
                       "at": "ISO 时间戳"},
            "steps": [],
        }, open(ledger, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for a in AGENTS:
        p = os.path.join(root, "breakpoint", "%s_log.json" % a.lower())
        if not os.path.exists(p):
            json.dump({"agent": a, "run_at": None, "steps": []},
                      open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("工作区已就绪：", root)
    for d in ("scripts", "output", "breakpoint", "literature"):
        print("  %-12s %s" % (d + "/", os.path.join(root, d)))

if __name__ == "__main__":
    main()
