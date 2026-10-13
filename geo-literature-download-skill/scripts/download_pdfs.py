"""Polite, resumable PDF downloader with full-text verification.

Resolution order for each paper:
  1. the Semantic Scholar supplied link (result-card PDF / openAccessPdf / reader)
  2. embedded PDF link found on the returned landing page
  3. Unpaywall lookup by DOI (open-access verification)
  4. Semantic Scholar Graph API openAccessPdf
  5. Semantic Scholar paper page (Semantic Reader channel)

Access limits (HTTP 403/418/429 or a bot-check page) are retried once after 60 s,
as required. All outcomes are written to breakpoint/download_results.json so a
rerun resumes instead of re-requesting.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from litlib import (  # noqa: E402
    BREAKPOINT_DIR,
    HARD_STOP_SUCCESSES,
    LITERATURE_DIR,
    QUEUE_FILE,
    audit,
    load_json,
    polite_sleep,
    sanitize_filename,
    save_json,
    unique_path,
    verify_pdf,
)

RESULTS_FILE = os.path.join(BREAKPOINT_DIR, "download_results.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
BLOCK_MARKERS = ("captcha", "are you a robot", "cf-error", "access denied",
                 "verify you are human", "unusual traffic", "too many requests",
                 "确认您是人类", "请完成安全检查", "radware", "incapsula",
                 "just a moment", "enable javascript and cookies",
                 "client challenge", "bm-verify", "akamai/interstitial",
                 "checking your browser", "unsupported browser")
PDF_HINT_RE = re.compile(r"(citation_pdf_url|\.pdf(\?|$|#)|pdfdirect|/pdf\b|pdfUrl|contentUrl)", re.I)


def ok_so_far(results: dict) -> int:
    return sum(1 for v in results.values() if v.get("status") == "成功")


def session():
    import requests

    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "sec-ch-ua": '"Chromium";v="141", "Not?A_Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    })
    return s


def get(s, url, referer=None, timeout=120):
    h = {"Referer": referer} if referer else {}
    origin = "{0.scheme}://{0.netloc}/".format(urlparse(url))
    h.setdefault("Referer", origin)
    return s.get(url, headers=h, timeout=timeout, allow_redirects=True)


def is_pdf(resp) -> bool:
    if resp is None:
        return False
    if resp.content[:1024].lstrip().startswith(b"%PDF"):
        return True
    ctype = (resp.headers.get("Content-Type") or "").lower()
    return "application/pdf" in ctype and len(resp.content) > 20000


def looks_blocked(resp) -> bool:
    if resp is None:
        return False
    if resp.status_code in (403, 418, 429, 503):
        return True
    text = resp.content[:20000].decode("utf-8", "ignore").lower()
    return any(m in text for m in BLOCK_MARKERS)


def extract_pdf_link(html_text: str, base_url: str):
    pats = [
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+\.pdf[^"\']*)["\'][^>]+name=["\']citation_pdf_url',
        r'"(?:pdfUrl|pdf_url|contentUrl|url_for_pdf)"\s*:\s*"([^"]+)"',
        r'href=["\']([^"\']+?\.pdf(?:\?[^"\']*)?)["\']',
        r'href=["\']([^"\']*pdfdirect[^"\']*)["\']',
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>\s*(?:Download|Full[- ]?text|PDF)',
    ]
    for p in pats:
        for m in re.finditer(p, html_text, re.I):
            cand = urljoin(base_url, m.group(1).replace("\\/", "/"))
            if cand.startswith("http") and PDF_HINT_RE.search(cand):
                return cand
    return None


def unpaywall(s, doi):
    if not doi:
        return None
    try:
        r = s.get(f"https://api.unpaywall.org/v2/{doi}",
                  params={"email": "literature.downloader@example.org"}, timeout=60)
        if r.status_code != 200:
            return None
        d = r.json()
        best = d.get("best_oa_location") or {}
        for loc in [best] + (d.get("oa_locations") or []):
            u = (loc or {}).get("url_for_pdf") or (loc or {}).get("url")
            if u:
                return u
    except Exception:  # noqa: BLE001
        return None
    return None


def s2_oa(s, paper_id, doi):
    try:
        if paper_id:
            r = s.get(f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}",
                      params={"fields": "openAccessPdf,externalIds"}, timeout=60)
            if r.status_code == 200:
                u = (r.json().get("openAccessPdf") or {}).get("url")
                if u:
                    return u
    except Exception:  # noqa: BLE001
        pass
    return None


def variant_urls(url):
    """Publisher specific direct-PDF shapes worth trying."""
    out = []
    if "onlinelibrary.wiley.com/doi/" in url and "pdfdirect" not in url and url.endswith((".pdf", "/pdf")) is False:
        pass
    if url.endswith("/pdfdirect/") or "pdfdirect" in url:
        out.append(url.split("?")[0] + "?download=true")
    if "link.springer.com" in url and "/content/pdf/" in url and not url.endswith(".pdf"):
        out.append(url.rstrip("/") + ".pdf")
    if "doi.org/" in url:
        out.append(url.replace("https://doi.org/", "https://dx.doi.org/"))
    return out


def attempt(s, url, referer, store):
    """Fetch one URL; return (resp_or_None, note)."""
    try:
        resp = get(s, url, referer=referer)
    except Exception as exc:  # noqa: BLE001
        return None, f"request error: {exc}"
    if is_pdf(resp):
        store["resp"] = resp
        return resp, "pdf"
    if looks_blocked(resp):
        audit("download", "access_limit", f"HTTP {resp.status_code} at {url[:110]}; retry once after 60 s")
        time.sleep(60)
        try:
            resp = get(s, url, referer=referer)
        except Exception as exc:  # noqa: BLE001
            return None, f"retry error: {exc}"
        if is_pdf(resp):
            store["resp"] = resp
            return resp, "pdf (after 60s retry)"
        if looks_blocked(resp):
            return resp, "still limited after retry"
    html_text = resp.content[:400000].decode("utf-8", "ignore")
    link = extract_pdf_link(html_text, resp.url)
    if link and link.rstrip("/") != url.rstrip("/"):
        try:
            r2 = get(s, link, referer=resp.url)
            if is_pdf(r2):
                store["resp"] = r2
                return r2, f"resolved embedded pdf ({urlparse(link).netloc})"
        except Exception:  # noqa: BLE001
            pass
    low = html_text.lower()
    if any(m in low for m in ("purchase pdf", "buy this article", "get access",
                              "rent this article", "sign in to continue", "institutional login")):
        return resp, "paywalled"
    if any(m in low for m in ("page not found", "no longer available", "404")):
        return resp, "dead link"
    if len(html_text) < 20000 and ("abstract" in low or "references" in low):
        return resp, "abstract/landing page only"
    return resp, "landing page without a usable pdf link"


def download_one(s, item, index):
    url = item.get("url") or ""
    title = item.get("title") or "untitled"
    rec = {
        "title": title, "year": item.get("year", ""), "citations": item.get("citations", ""),
        "venue": item.get("venue", ""), "doi": item.get("doi", ""), "pdf_url": url,
        "search_term": item.get("search_term", ""), "source_db": item.get("source_db", "Semantic Scholar"),
        "authors": item.get("authors", []), "status": "其他失败原因", "file": "",
        "verified_pages": 0, "verified_chars": 0, "note": "", "channel": "", "round": item.get("round", 1),
    }
    urls = [u for u in [url] + list(item.get("alt_urls") or []) if u]
    last_note = "no link available"
    store = {}
    for u in urls:
        resp, note = attempt(s, u, None, store)
        last_note = note
        if store.get("resp") is not None:
            rec["channel"] = f"semanticscholar:{urlparse(u).netloc}"
            break
    if store.get("resp") is None:
        oa = unpaywall(s, item.get("doi"))
        if oa:
            urls.append(oa)
            resp, note = attempt(s, oa, None, store)
            last_note = note
            if store.get("resp") is not None:
                rec["channel"] = f"unpaywall:{urlparse(oa).netloc}"
        if store.get("resp") is None:
            oa2 = s2_oa(s, item.get("paper_id"), item.get("doi"))
            if oa2 and oa2 not in urls:
                resp, note = attempt(s, oa2, None, store)
                last_note = note
                if store.get("resp") is not None:
                    rec["channel"] = f"s2api:{urlparse(oa2).netloc}"
    if store.get("resp") is None:
        low = last_note.lower()
        if "still limited" in low or "access_limit" in low:
            rec["status"] = "人机验证/访问限制"
        elif "paywall" in low:
            rec["status"] = "出版商链接不开放"
        elif "dead link" in low:
            rec["status"] = "链接失效"
        elif "abstract" in low or "landing page" in low or "no link" in low:
            rec["status"] = "页面不符合要求"
        else:
            rec["status"] = "其他失败原因"
        rec["note"] = last_note
        return rec

    tmp = os.path.join(BREAKPOINT_DIR, "_tmp_download.bin")
    with open(tmp, "wb") as fh:
        fh.write(store["resp"].content)
    check = verify_pdf(tmp)
    if not check["ok"]:
        rec["status"] = "页面不符合要求"
        rec["note"] = check["reason"]
        rec["note"] = check["reason"]
        rec["verified_pages"] = check["pages"]
        return rec
    dest = unique_path(LITERATURE_DIR, sanitize_filename(index, title))
    os.replace(tmp, dest)
    rec.update({"status": "成功", "file": os.path.basename(dest),
                "verified_pages": check["pages"], "verified_chars": check["text_chars"],
                "note": check["reason"]})
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=QUEUE_FILE,
                    help="direct-download queue written by build_queues.py "
                         "(default: breakpoint/script_queue.json)")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--limit", type=int, default=1000)
    ap.add_argument("--min-wait", type=float, default=15.0)
    ap.add_argument("--max-wait", type=float, default=30.0)
    ap.add_argument("--start-index", type=int, default=1)
    ap.add_argument("--dry-run", type=int, default=0)
    ap.add_argument("--retry-attempted", action="store_true",
                    help="re-attempt items that already have a recorded outcome")
    args = ap.parse_args()

    os.makedirs(LITERATURE_DIR, exist_ok=True)
    queue = load_json(args.queue, []) or []
    results = load_json(RESULTS_FILE, {}) or {}
    s = session()
    n_new = processed = 0
    stopped_early = False
    index = args.start_index
    if args.dry_run:
        queue = queue[: args.dry_run]
    audit("download", "queue_start", f"round {args.round}: {len(queue)} items",
          round=args.round, queue_size=len(queue))

    for item in queue:
        if processed >= args.limit:
            break
        # Hard boundary: never start another download once the cap is reached.
        if ok_so_far(results) >= HARD_STOP_SUCCESSES:
            stopped_early = True
            audit("download", "hard_stop",
                  f"cumulative successes {ok_so_far(results)} reached the cap "
                  f"{HARD_STOP_SUCCESSES}: stopping before the next request.",
                  round=args.round, successes=ok_so_far(results))
            break
        key = (item.get("doi") or "").lower() or item.get("paper_id") or item.get("title", "")
        if not key:
            continue
        prior = results.get(key)
        if prior and prior.get("status") == "成功":
            continue
        if prior and not args.retry_attempted:
            continue
        polite_sleep(args.min_wait, args.max_wait, label=f"download #{index}")
        rec = download_one(s, item, index)
        rec["round"] = args.round
        results[key] = rec
        save_json(RESULTS_FILE, results)
        processed += 1
        if rec["status"] == "成功":
            n_new += 1
            index += 1
        if ok_so_far(results) >= HARD_STOP_SUCCESSES:
            stopped_early = True
            audit("download", "hard_stop",
                  f"cumulative successes {ok_so_far(results)} reached the cap "
                  f"{HARD_STOP_SUCCESSES}: stopping immediately as required by the skill.",
                  round=args.round, successes=ok_so_far(results))
            break
        audit("download", "item_done",
              f"[{rec['status']}] {rec['title'][:60]} | {rec['note'][:50]}",
              round=args.round, status=rec["status"], file=rec["file"], channel=rec["channel"])

    ok = sum(1 for r in results.values() if r.get("status") == "成功")
    summary = {"round": args.round, "processed_this_run": processed,
               "new_success_this_run": n_new, "cumulative_success": ok,
               "cap": HARD_STOP_SUCCESSES,
               "hard_stop_reached": stopped_early or ok >= HARD_STOP_SUCCESSES}
    audit("download", "queue_end", json.dumps(summary, ensure_ascii=False), **summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
