#!/usr/bin/env python3
"""geodatabase-rate-skill：抓取官方页面快照到 literature/，并登记可达性。

用法：
  python fetch_evidence.py <url> [<url> ...] [--root 工作目录]
  python fetch_evidence.py --from-csv output/labelled_x.csv --columns 数据库官网网址入口 数据库下载网址入口

产出：literature/<url slug>.txt（含 URL/STATUS/正文摘要）、breakpoint/evidence_index.json
不可达页面会记录 error 与建议（改用官方替代页或 Wayback 快照），不留空。
"""
import argparse, datetime, json, os, re, sys

import requests
from bs4 import BeautifulSoup

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) chrome/124.0 Safari/537.36"}

def slug(url):
    s = re.sub(r"^https?://", "", url.strip())
    s = re.sub(r"[^0-9A-Za-z._-]+", "_", s)
    return s.strip("_")[:120] or "index"

def grab(url, timeout=30, limit=20000):
    r = requests.get(url, headers=H, timeout=timeout, allow_redirects=True)
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    txt = soup.get_text("\n")
    txt = re.sub(r"[ \t]{2,}", " ", txt)
    lines = [l.strip() for l in txt.split("\n") if l.strip()]
    return r.status_code, "\n".join(lines)[:limit]

sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台中文输出


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--root", default=os.getcwd())
    ap.add_argument("--from-csv", default=None)
    ap.add_argument("--columns", nargs="*", default=["数据库官网网址入口", "数据库下载网址入口"])
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    lit, bp = os.path.join(root, "literature"), os.path.join(root, "breakpoint")
    os.makedirs(lit, exist_ok=True); os.makedirs(bp, exist_ok=True)

    urls = list(a.urls)
    if a.from_csv:
        import csv
        for row in csv.DictReader(open(os.path.join(root, a.from_csv), encoding="utf-8-sig")):
            for c in a.columns:
                u = (row.get(c) or "").strip()
                if u and u not in urls:
                    urls.append(u)

    idx_path = os.path.join(bp, "evidence_index.json")
    idx = json.load(open(idx_path, encoding="utf-8")) if os.path.exists(idx_path) else {}
    for u in urls:
        rec = {"url": u, "fetched_at": datetime.datetime.now().isoformat(timespec="seconds")}
        try:
            st, txt = grab(u)
            fn = slug(u) + ".txt"
            open(os.path.join(lit, fn), "w", encoding="utf-8").write("URL: %s\nSTATUS: %s\n\n%s\n" % (u, st, txt))
            rec.update({"status": st, "snapshot": "literature/" + fn})
        except Exception as e:
            rec.update({"status": None, "error": type(e).__name__ + ": " + str(e)[:160],
                        "note": "原页面不可达：请改用官方替代页（机构主页/开发者文档/API 文档/DOI 落地页）或 Wayback 快照，并在证据字段注明"})
        idx[u] = rec
        print(u, "->", rec.get("status"), rec.get("error", ""))
    json.dump(idx, open(idx_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("evidence_index.json 已更新（%d 条）" % len(idx))

if __name__ == "__main__":
    main()
