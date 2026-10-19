#!/usr/bin/env python3
"""geodatabase-rate-skill：实测最高被引次数（CrossRef 优先，DataCite / OpenAlex 兜底）。

用法：
  python cites.py doi 10.1175/BAMS-D-11-00094.1 [--out breakpoint/cites.json]
  python cites.py query "An Overview of CMIP5 and the Experiment Design"
  python cites.py batch queries.txt          # 每行一条：DOI 或检索式
  python cites.py batch queries.txt --out breakpoint/cites.json

输出含 cites（精确数字）与 title/doi/来源，禁止估测；无法命中时返回 null 并给出已尝试的来源。
"""
import argparse, io, json, os, sys, time

import requests

UA = {"User-Agent": "geodatabase-rate-skill/1.0 (mailto:labeller@example.org)"}
SRC = ["CrossRef", "DataCite", "OpenAlex"]

def _get(url, params=None, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            time.sleep(2 + 2 * i)
        except Exception:
            time.sleep(2 + 2 * i)
    return None

def crossref_doi(doi):
    d = _get("https://api.crossref.org/works/" + doi)
    if not d:
        return None
    m = d["message"]
    return {"source": "CrossRef", "doi": m.get("DOI"), "cites": m.get("is-referenced-by-count"),
            "title": (m.get("title") or [""])[0],
            "year": (m.get("issued", {}).get("date-parts", [[None]])[0] or [None])[0]}

def crossref_query(q, rows=6):
    d = _get("https://api.crossref.org/works", {"query.bibliographic": q, "rows": rows,
             "select": "DOI,title,is-referenced-by-count,issued,container-title"})
    if not d:
        return []
    out = []
    for it in d["message"]["items"]:
        out.append({"source": "CrossRef", "doi": it.get("DOI"), "cites": it.get("is-referenced-by-count"),
                    "title": (it.get("title") or [""])[0][:160],
                    "year": (it.get("issued", {}).get("date-parts", [[None]])[0] or [None])[0]})
    return out

def datacite(q, rows=6):
    d = _get("https://api.datacite.org/dois", {"query": q, "page[size]": rows})
    if not d:
        return []
    out = []
    for it in d.get("data", []):
        at = it.get("attributes", {})
        titles = at.get("titles") or [{}]
        out.append({"source": "DataCite", "doi": at.get("doi"), "cites": at.get("citationCount"),
                    "title": (titles[0].get("title") or "")[:160], "year": at.get("publicationYear")})
    return out

def openalex(q, rows=6):
    d = _get("https://api.openalex.org/works", {"search": q, "per-page": rows})
    if not d:
        return []
    out = []
    for it in d.get("results", []):
        out.append({"source": "OpenAlex", "doi": (it.get("doi") or "").replace("https://doi.org/", ""),
                    "cites": it.get("cited_by_count"), "title": (it.get("title") or "")[:160],
                    "year": it.get("publication_year")})
    return out

def lookup(q):
    """Return the best measured citation count for a DOI or a free-text query.

    A DOI query must resolve to *that* DOI: if CrossRef has no record, the
    text-search fallbacks are only accepted when the hit DOI matches exactly
    (otherwise a bibliographic search can return an unrelated paper).
    """
    res = {"query": q, "attempts": []}
    is_doi = q.lower().startswith("10.") and "/" in q
    if is_doi:
        r = crossref_doi(q)
        if r:
            res["attempts"].append(r)
            if r.get("cites") is not None:
                res.update({"best": r, "source": r["source"], "cites": r["cites"], "title": r["title"]})
                return res
        want = q.lower()
        time.sleep(1)  # CrossRef 限速：距上次 CrossRef 请求 ≥1s
        for fn in (crossref_query, datacite, openalex):
            try:
                hits = fn(q)
            except Exception:
                hits = []
            res["attempts"].extend(hits)
            exact = [h for h in hits if (h.get("doi") or "").lower() == want and h.get("cites") is not None]
            if exact:
                best = max(exact, key=lambda h: h["cites"])
                res.update({"best": best, "source": best["source"], "cites": best["cites"], "title": best["title"]})
                return res
        res.update({"best": None, "source": None, "cites": None, "title": None})
        return res
    for fn in (crossref_query, datacite, openalex):
        try:
            hits = fn(q)
        except Exception:
            hits = []
        res["attempts"].extend(hits)
        hit = [h for h in hits if h.get("cites") is not None]
        if hit:
            best = max(hit, key=lambda h: h["cites"])
            res.update({"best": best, "source": best["source"], "cites": best["cites"], "title": best["title"]})
            return res
    res.update({"best": None, "source": None, "cites": None, "title": None})
    return res


sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台中文输出


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["doi", "query", "batch"])
    ap.add_argument("arg")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    items = [l.strip() for l in io.open(a.arg, encoding="utf-8") if l.strip()] if a.mode == "batch" else [a.arg]
    out = []
    for i, q in enumerate(items):
        if i:
            time.sleep(1)  # CrossRef 限速：批量模式下条目间 ≥1s
        r = lookup(q)
        out.append(r)
        print("%s | cites=%s | %s | %s" % (q, r["cites"], r["source"], (r["title"] or "")[:90]))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("已写出", a.out)

if __name__ == "__main__":
    main()
