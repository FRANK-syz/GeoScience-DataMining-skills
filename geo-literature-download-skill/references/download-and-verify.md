# 下载与全文验证

## 1. 通道顺序

对每篇候选按下列顺序解析，命中即停（`download_pdfs.py` 已实现）：

1. **Semantic Scholar 提供的直链**（卡片 PDF / `openAccessPdf.url`）——命中即下载；
2. **Semantic Reader**（`https://www.semanticscholar.org/reader/<paperId>`）——该页含托管 PDF 的下载链接，**视为有效原文链接，不得因其不是直链而判为无法下载**；同一篇有多个渠道时**优先用 Reader**；
3. **落地页内嵌 PDF 链接**：请求返回的页面里找 `<meta name="citation_pdf_url">`、`"pdfUrl"/"contentUrl"`、`href="...pdf"`、`href="...pdfdirect..."`、以及文本为 Download / Full text / PDF 的 `<a>`；
4. **Unpaywall（按 DOI）**：`https://api.unpaywall.org/v2/<DOI>?email=<email>` 取 `best_oa_location.url_for_pdf`；
5. **Semantic Scholar API**：`/graph/v1/paper/<id>?fields=openAccessPdf`；
6. **出版商原文页**：打开落地页找 Download / Download PDF 入口再下载。

链接实际指向出版商原文页时（Wiley、ACP 等响应较慢）**要等页面加载完**，不要快速判定为「原文获取受限制」。

## 2. 请求头与礼貌

- 使用真实浏览器 UA（如 Chrome 141）与 `Accept: text/html,...,application/pdf`、`Accept-Language`、`Referer` = 链接 origin。
- 每次下载前随机等待 **15–30 秒**。
- HTTP 403 / 418 / 429 / 503 或判定为人机验证页 → **等 60 秒重试 1 次**。

## 3. 人机验证 / 封锁标记

页面文本出现下列任一即视为被拦截，不可作为全文保存：

```
captcha, are you a robot, cf-error, access denied, verify you are human,
unusual traffic, too many requests, 确认您是人类, 请完成安全检查,
radware, incapsula, just a moment, enable javascript and cookies,
client challenge, bm-verify, akamai/interstitial,
checking your browser, unsupported browser
```

## 4. 浏览器代下载（JS 挑战出版商）

MDPI、Springer、Wiley、ScienceDirect、Nature、OUP、IOP 等会弹 JS 人机验证，纯 HTTP 会被 403。改由**浏览器标签页**打开落地页（优先用从 PDF 链接反推的直连落地页，跳过 `doi.org` 跳转链），等挑战自行通过后点击下载入口并保存文件：

```
selectors = ['a[href*="/content/pdf/"]', 'a[href*="pdfdirect"]',
             'a[href$="/pdf"]', 'a[href*=".pdf"]', '#pdfLink']
# tab.playwright.locator(sel).downloadMedia() -> 本地文件
```

- 逐个选择器尝试，命中后把文件落到下载目录，`note` 记下命中的选择器（便于复现）。
- **不要**在浏览器里打开 `data:text/html` 等被 URL 策略拦截的地址。
- 下载完统一交给 `ingest_browser_downloads.py`：校验通过才移入 `literature/` 并登记为 `成功`。
- 网络层错误（如 `net::ERR_CONNECTION_CLOSED`）记 `其他失败原因`，不算成功。

## 5. 全文验证判据（只有实际保存且通过才记 `成功`）

PDF：

- 文件 ≥ 20 KB，且开头含 `%PDF` 魔数；
- 用 `pypdf` 可解析，**≥ 1 页**；
- 前 8 页可提取文本 **≥ 1500 字符**（纯扫描图片、空壳 PDF 不合格）；
- 不是 HTML/登录/错误页被改名成 `.pdf`。

HTML 全文：必须是完整正文页（非摘要页、引用页、登录页、错误跳转页）。

**一律不算成功**：摘要页、引用页、Supporting Information、Reviewer Comment / 审稿意见、404 与错误跳转页、登录页、社论 / 政策法律评论、章节型资料、学位论文、出版商封面或 OA 通知页、单页会议摘要、无关网页。

**非地球科学领域的 PDF 直接删除**，且不记为成功收集（把 DOI 写进 `breakpoint/exclusions.json` 以便审计）。

## 6. 状态取值

`是否下载成功` 只能取：

| 状态 | 判定 |
| --- | --- |
| `成功` | 已保存到本地并通过上述全文验证 |
| `人机验证/访问限制` | captcha / Radware / Cloudflare / 403 等，重试后仍被拦 |
| `页面不符合要求` | 落地页/文件不是合格全文（摘要页、SI、封面页、加密不可读等） |
| `出版商链接不开放` | 命中付费墙或需订阅 |
| `链接失效` | 404 / 死链 |
| `其他失败原因` | 网络错误、解析异常等其余情况 |

## 7. 领域与可用性复核

下载完成不等于通过：收尾后必须先用 `audit_relevance.py` 逐篇确认是**地球科学**全文（正文术语 + 期刊名 + 学科字段三重佐证；只有 `subsurface`/`fracture` 等词面重合的材料学、化学论文会被判为 `non-geoscience` 或 `review`），再用 `verify_deliverables.py` 逐篇重新打开解析，确认 PDF **可用**（可读、≥1 页、正文文本量达标）。两关都不通过就不算有效收集。

## 8. 去重

同一文献的不同版本/来源按 **DOI + 标题**去重：预印本（如 `10.5194/xx-2020-15`、`egusphere`、arXiv 版本）与正式版同时存在时**保留正式版**，被淘汰的版本标记后从 `literature/` 删除。重复文件名通过 `unique_path()` 加稳定哈希后缀，绝不覆盖无关文件。
