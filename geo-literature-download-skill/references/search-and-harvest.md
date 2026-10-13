# 检索与抓取（Semantic Scholar）

## 1. 检索 URL

浏览器打开 Semantic Scholar 检索页，务必保持页面可见：

```
https://www.semanticscholar.org/search?q=<url-encoded-term>&sort=relevance&pdf=true&year%5B0%5D=<min>&year%5B1%5D=<max>&page=<N>
```

- `pdf=true` —— 即网页端的 **Has PDF** 筛选，排除没有下载入口的条目。
- `year[0]` / `year[1]` —— 时间窗口，默认「当前年份往前 15 年」（例：2026 年运行时取 2011–2026）。
- `sort=relevance`，`page` 从 1 开始翻页。
- 每个检索词目标 **≥ 40 条**候选，按 10 条/页约翻 4–5 页。

示例（可整段复制）：

```
https://www.semanticscholar.org/search?q=fracture%20connectivity&sort=relevance&pdf=true&year%5B0%5D=2011&year%5B1%5D=2026&page=2
```

## 2. 结果卡片字段

结果页每页 10 张卡片，`class="cl-paper-row"`，带 `data-paper-id`。卡片上可直接读到：

| 抓取字段 | 来源 |
| --- | --- |
| `paper_id` | 卡片的 `data-paper-id`（40 位十六进制） |
| `title` | 卡片标题链接文本 |
| `authors` | 作者列表 |
| `year` | 年份 |
| `venue` | 期刊/会议名（可能是 URL 编码，如 `Rock%20Mechanics%20and%20Rock%20Engineering`，需解码） |
| `fields` | 学科标签（如 `Engineering, Geology`），用于地球科学相关性初判 |
| `pdf_url` | 卡片上的 PDF / 「Semantic Reader」链接 |
| `publisher_url` | 卡片上的 `https://doi.org/<DOI>` 链接 |
| `paper_url` | 卡片标题的 `semanticscholar.org/paper/...` 链接 |

**被引数不在结果页渲染**，必须由 `paper/batch` 富化补齐（见 §4）。

## 3. DOM 抽取

在浏览器中执行下面这段 JS，把当前页所有卡片读成 JSON（字段与 `breakpoint/harvest_raw.json` 的行结构一致）：

```js
(() => Array.from(document.querySelectorAll('.cl-paper-row')).map(r => {
  const links = Array.from(r.querySelectorAll('a[href]')).map(a => a.href);
  const paper = links.find(h => h.includes('/paper/'));
  const doi   = links.find(h => h.includes('doi.org/'));
  const pdf   = links.find(h => /semanticscholar\.org\/reader\/|pdfs\.semanticscholar\.org|\.pdf|\/pdf|download/i.test(h));
  const txt   = (sel) => { const e = r.querySelector(sel); return e ? e.textContent.trim() : ''; };
  const titleNode = r.querySelector('a[data-paper-id], h2 a, .cl-paper-title') || paper;
  return {
    paper_id:      r.getAttribute('data-paper-id') || (titleNode && titleNode.getAttribute('data-paper-id')) || '',
    title:         titleNode ? titleNode.textContent.trim() : txt('.cl-paper-title'),
    authors:       Array.from(r.querySelectorAll('.cl-paper-authors a, [class*=author]'))
                     .map(a => a.textContent.trim()).filter(Boolean),
    year:          txt('.cl-paper-pubdates').replace(/^.*?(\d{4}).*$/, '$1'),
    venue:         decodeURIComponent(txt('.cl-paper-venue') || txt('[class*=venue]')),
    fields:        txt('.cl-paper-fos'),
    pdf_url:       pdf || '',
    publisher_url: doi || '',
    paper_url:     paper || '',
    source_db:     'Semantic Scholar'
  };
}))
```

抓完一页后写入 `breakpoint/harvest_raw.json`（形如 `{ "<检索词>": [ {行}, ... ], ... }`），同一检索词内按 `paper_id` 去重，并记 `search_term` / `page`。摘要/引用页不抓，只抓有 PDF 的卡片。

## 4. 富化（`enrich_candidates.py`）

对全部去重后的 `paper_id` 调 **Semantic Scholar Graph API 的批量接口**——每个检索词一次请求，不要逐条查询：

```
POST https://api.semanticscholar.org/graph/v1/paper/batch
     ?fields=title,year,citationCount,venue,externalIds,openAccessPdf,authors,publicationTypes,isOpenAccess
Body: { "ids": ["<paperId>", ...] }        # 每次最多 100 个 id
```

- `citationCount` → 被引数；`venue` → 期刊名全称（`externalIds.DOI` → DOI；`openAccessPdf.url` → 开放全文链接；`authors` → 作者）。
- 卡片上的 `venue` 若等于学科字段或只是 2–3 个学科名拼接，视为无效并从 API 取。
- 返回码非 200 时等待 20 s 重试，最多 3 次；块与块之间间隔 8 s。
- 输出 `breakpoint/candidates.json`，每篇候选带 `search_term` 与 `search_terms` 列表。
- 同时调用 `litlib.validate_search_terms()` 校验**累计检索词 ≤ 6**，超出的记录审计并丢弃。

## 5. 礼貌访问

- **翻页、富化、下载之间统一随机等待 15–30 秒**（`litlib.polite_sleep(15, 30)`）。
- 不要并发、不要循环重试同一个 URL。
- Semantic Scholar 出现人机验证页（“确认您是人类” / Cloudflare 挑战）时：**等待约 10 分钟，然后从流程开头重试一次**（仅 1 次）。若仍然受限，记 `人机验证/访问限制`。
- 其他站点的人机验证/访问限制：等 1 分钟重试 1 次，仍失败则记录为 `人机验证/访问限制`。
