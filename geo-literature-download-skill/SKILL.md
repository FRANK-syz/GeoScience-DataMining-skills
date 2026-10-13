---
name: geo-literature-download-skill
description: 地球科学主题的文献批量检索与开放获取全文下载流水线——在 Semantic Scholar 上按有限检索词分轮检索，逐条验证并下载可读全文，去重并剔除不符合要求的页面，最终产出检索明细表与成功清单表。适用于用户给出地球科学主题并要求成批检索、下载或整理论文全文（含「下载至少 N 篇」「生成文献清单」类要求）的场景；不适用于单篇论文查找、参考文献格式整理或纯综述写作。
metadata:
  short-description: 地球科学文献批量检索与全文下载
---

# geo-literature-download-skill

围绕输入主题，检索、验证并下载去重后的开放获取地球科学全文，产出两张表和一个 PDF 文件夹。

## 硬性参数

- **检索词上限：累计不超过 6 个**（核心词 + 同义词/缩写/词形变化的总数）。达到 6 个即停止扩展，即使主题还能拆出更多名词。
- **成功上限：累计成功达到 80 篇即立刻结束获取流程**（硬边界，不得突破）。每下载成功一篇就检查一次；达到 80 时不再发起任何检索或下载请求，即使当前轮次尚未跑完，直接进入收尾、复核与汇报。因此 `literature/` 中的文件数永远 ≤ 80。
- 目标数量默认 50 篇；成功数达到目标且未触及上限时，**完成当前轮次后**停止。用户可指定其他目标数量。
- 最多 6 轮。时间窗口默认当前年份往前 15 年，用户可覆盖。
- 排除专利、书籍、学位论文、会议摘要与纯引用条目。

## 工作目录

在任务工作目录下建立并在整个流程中复用：

- `breakpoint/` — 中间数据与审计记录（`audit_log.jsonl` 为逐步审计，任何一步都可断点重启）
- `scripts/` — 从本技能 `scripts/` 复制过来的脚本副本（保证任务自包含、可复现）
- `literature/` — 下载的 PDF
- `output/` — 表格与报告

所有脚本通过 `LIT_ROOT` 环境变量或当前工作目录定位这些文件夹；运行时把工作目录设为任务目录，或先 `set LIT_ROOT=<任务目录>`。

运行前先 `pip install -r requirements.txt`（`pypdf`、`requests`）。

## 流程

### 1. 主题分析与检索词

从主题中提取 1–3 个核心地球科学名词作为核心词：去掉方法论（机器学习、深度学习、反演、优化等）、形容词、修饰词与无关背景。每个核心词再生成 1–2 个同义词、缩写、近义词或词形变化。**总数封顶 6 个**，不要拼接检索词。

生成后**输出全部检索词并暂停**，询问用户是否确认使用；确认后再继续。

### 2. 浏览器检索

使用浏览器（Computer Use / 内置浏览器）在 Semantic Scholar 检索，保持页面打开：加上「Has PDF」与年份过滤，用 `page=N` 翻页，每个检索词目标 ≥40 条候选。翻页与下载请求之间加入 **15–30 秒随机等待**。详细 URL 参数、结果卡片字段与 DOM 抽取脚本见 [references/search-and-harvest.md](references/search-and-harvest.md)。

遇到 Semantic Scholar 人机验证页：等待约 10 分钟后从头重试 **1 次**即可。其他站点出现人机验证/访问限制时等待 1 分钟重试 1 次，仍失败则记为「人机验证/访问限制」。

### 3. 富化与建队列

用 Semantic Scholar `paper/batch` 接口按检索词分批补齐被引数、完整期刊名、DOI、作者与 `openAccessPdf`（每个检索词 1 次请求即可，不要逐条查询）。随后把候选拆成两条通道：

- 直链通道（Semantic Scholar 托管 PDF、机构库、OSTI、arXiv、diva 等）→ 走 `download_pdfs.py`
- JS 挑战通道（MDPI、Springer、Wiley、ScienceDirect、Nature、OUP 等）→ 走浏览器下载

### 4. 下载与全文验证

按 [参考流程](references/download-and-verify.md) 逐条解析：Semantic Scholar 直链/Reader → 落地页内嵌 PDF 链接 → Unpaywall（按 DOI）→ Semantic Scholar API → 出版商页面。下载间隔 15–30 秒。

**只有实际保存到本地并通过验证的全文才算成功。** 摘要页、引用页、登录页、404/错误跳转页、Supporting Information、Reviewer Comment、社论/政策评论、章节型资料、学位论文、出版商封面或 OA 通知页、单页会议摘要一律不算成功。纳入范围内的必须是完整的地球科学论文，非地球科学 PDF 直接删除且不记为成功。

「是否下载成功」字段只能取：成功、人机验证/访问限制、页面不符合要求、出版商链接不开放、链接失效、其他失败原因。

### 5. 收尾与排重

先跑 **`audit_relevance.py`** 逐篇复核领域相关性（判定为 `non-geoscience` 的条目在 `--apply` 时写入 `breakpoint/exclusions.json`），再跑收尾脚本：剔除非地球科学条目、剔除学位论文/封面页/单页无正文条目、按 DOI 与标题去重（预印本保留正式版）、重新连续编号为 `NNN_标题.pdf`。细则与命名规范见 [references/outputs-and-audit.md](references/outputs-and-audit.md)。

### 6. 表格、报告与轮次循环

生成 `output/literature_search_info.csv`（检索过的全部条目，一条 = 一个「论文 × 检索词」）与 `output/literature_download_inventory.csv`（成功清单）。每轮结束汇报：浏览条目数、本轮新增成功数、累计成功数、是否满足数量条件。

后续轮次规则：

- 偶数轮：等待 1 分钟后重试此前标记为「人机验证/访问限制」的条目（可派临时子 Agent 协助下载）。
- 奇数轮：依据已有关键词的近义词或同领域常用科学词新增 1–2 个检索词——**但总数始终不超过 6 个**；若已达上限，则改为对已有检索词加深翻页，不再新增检索词。
- 每轮结束后检查终止条件：累计成功 **≥ 80** → 立即停止（硬边界）；达到目标且未触及上限 → 完成本轮后停止；4 轮后仍不足目标 → 说明原因。

### 7. 复核与交付校验（结束前必做）

流程结束（或触及 80 篇上限而终止）后，**必须**依次运行，三关全部通过才算交付：

1. `audit_relevance.py`（可加 `--apply`）——逐篇判定领域相关性，产出 `output/relevance_report.md` 与 `breakpoint/relevance_audit.json`；`non-geoscience` 的条目交 `finalize_literature.py` 剔除，`review` 的条目需人工/Agent 确认后再决定去留。
2. `finalize_literature.py` —— 按 `exclusions.json` 剔除并重新编号（确保清单与文件同步）。
3. `verify_deliverables.py` —— **复核清单数量是否有误**：`literature/` 文件数 = 清单记录数 = 成功记录数；清单每一行都能找到对应文件、每个文件都被清单收录且只被认领一次；逐篇重新打开解析确认**可用**（非空白、非扫描、非摘要页）；并检查是否突破 80 篇上限。产出 `output/verification_report.md`、`breakpoint/verification_report.json`；**一旦不一致会以非 0 退出码失败**，必须修复后重跑，不得带着不一致交付。

数量不一致时的处理：重跑 `finalize_literature.py` 与 `build_tables.py`，再跑 `verify_deliverables.py`；仍不一致则必须如实报告差异（缺失文件 / 多余文件 / 重复认领逐条列出），不得虚构数量。

## 脚本

| 脚本 | 用途 |
| --- | --- |
| `litlib.py` | 公共工具：审计日志、断点状态、文件名规范化、PDF 全文校验 |
| `enrich_candidates.py` | 合并浏览器抓取的候选 JSON，批量富化并写出 `candidates.json` |
| `build_queues.py` | 生成直链队列与浏览器队列 |
| `download_pdfs.py` | 礼貌下载器（15–30 秒间隔、60 秒重试、多通道回退、断点续跑） |
| `ingest_browser_downloads.py` | 把浏览器下载的文件校验并移入 `literature/` |
| `audit_relevance.py` | 逐篇复核地球科学相关性，产出相关性报告并（`--apply`）写入剔除清单 |
| `finalize_literature.py` | 按剔除清单删除、去重、版本去重、重新编号 |
| `build_tables.py` | 生成两张交付表 |
| `verify_deliverables.py` | 交付复核：数量一致性 + 文件与清单逐条对应 + 逐篇可用性，不一致则非 0 退出 |
| `make_reports.py` | 生成轮次报告与最终报告（含复核结论） |

各脚本均支持 `--help`。运行顺序：`enrich_candidates.py` → `build_queues.py` → `download_pdfs.py` → `ingest_browser_downloads.py` → `audit_relevance.py` → `finalize_literature.py` → `build_tables.py` → `verify_deliverables.py` → `make_reports.py`。

## 参考

- [references/search-and-harvest.md](references/search-and-harvest.md) — 检索 URL、结果卡片字段、DOM 抽取脚本、富化接口
- [references/download-and-verify.md](references/download-and-verify.md) — 下载通道顺序、请求头、全文验证判据与失败归类
- [references/outputs-and-audit.md](references/outputs-and-audit.md) — 表格字段、状态枚举、命名与去重规则、审计与断点文件
