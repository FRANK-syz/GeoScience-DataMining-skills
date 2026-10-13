# 表格、命名与审计

## 1. 交付表

### `output/literature_search_info.csv`

记录**检索过的全部条目**，一条 = 一个「论文 × 检索词」；未下载成功的浏览条目也要记录；缺失信息留白。UTF-8-SIG 编码。

| 字段 | 说明 |
| --- | --- |
| 文章标题 | 论文标题 |
| 发表年份 | 年份 |
| 被引数 | `citationCount` |
| 期刊名全称 | 完整期刊/会议名（非学科标签） |
| DOI | 首选 DOI |
| 原文pdf下载地址 | Semantic Scholar 提供的 PDF / Reader 链接 |
| 是否下载成功 | 见下方枚举（未尝试/浏览过的为空白） |
| 检索词 | 该条命中的检索词 |
| 来源文献数据库 | 默认 `Semantic Scholar` |

### `output/literature_download_inventory.csv`

只含**成功下载**的文献，字段在检索表基础上加作者与来源检索式：

| 字段 |
| --- |
| 文章标题 / 作者（前三位，`; ` 分隔） / 发表年份 / 被引数 / 期刊名全称 / DOI / 原文pdf下载地址 / 来源检索式 / 来源文献数据库 |

`build_tables.py` 末行会打印 `success_records` / `pdf_files_on_disk` / `match` / `orphan_files`，三者必须一致。

## 2. 状态枚举（仅这 6 个值）

```
成功 | 人机验证/访问限制 | 页面不符合要求 | 出版商链接不开放 | 链接失效 | 其他失败原因
```

不在这 6 个值内的状态一律归一为 `其他失败原因`（`build_tables.norm()`）。

## 3. 文件命名

`NNN_标题.pdf`：

- `NNN` —— 3 位连续序号（`finalize_literature.py` 收尾时按标题重排为 001 起连续）；
- 标题 —— HTML 反转义 → NFKC 归一 → 去 Windows 非法字符 `< > : " / \ | ? *` 与控制符 → `&` 转 ` and ` → 只保留字母数字/空格/连字符/中日韩字符 → 折叠空格 → **转小写** → 截断到 110 字符 → 去尾部 `.`/空格；
- 空标题用 `untitled`；
- 已存在的同名文件用 `unique_path()` 追加 6 位标题哈希（再冲突则 `-2`、`-3`…），**禁止覆盖无关文件**；
- 收尾必须统一大小写、统一标点、去多余空格。

## 4. 去重与清洗

`finalize_literature.py` 顺序执行：

1. **学科剔除**：按 `breakpoint/exclusions.json` 的 `non_geo_dois` / `reject_prefixes` 删除非地球科学条目；
2. **严格校验**：删除学位论文、出版商封面/OA 通知页、Supporting Information / 审稿材料、单页无正文条目；
3. **完全相同标题** 去重（同 stem 只留一个）；
4. **近似标题版本去重**（相似度 > 0.93）：预印本与正式版并存时删预印本、留正式版；
5. **重新连续编号** 为 `NNN_标题.pdf`，并同步更新 `download_results.json` 里的 `file` 字段，保证清单与实际文件一致。

## 5. 目录结构

| 目录 | 内容 |
| --- | --- |
| `literature/` | 通过全文验证的 PDF |
| `output/` | `literature_search_info.csv`、`literature_download_inventory.csv`、`round{N}_report.md`、`Literature_Downloader_final_report.md`、`manual_download_needed.md`、`relevance_report.md`、`verification_report.md` |
| `scripts/` | 本次使用的脚本副本 |
| `breakpoint/` | 中间数据与审计 |

## 6. 断点与审计文件（`breakpoint/`）

| 文件 | 用途 |
| --- | --- |
| `audit_log.jsonl` | **逐步审计**：每一步（主题分析、检索、建队列、每次下载结果、收尾、出表、报告）追加一行，含时间戳与 `data`；重启后可据此还原进度 |
| `search_terms.json` | 确认使用的检索词及时间窗口 |
| `topic_analysis.json` | 主题分析：核心名词、被剔除的方法论词 |
| `harvest_raw.json` | 浏览器抓取的原始卡片（按检索词分组） |
| `candidates.json` | 富化后的去重候选 |
| `script_queue.json` / `browser_queue.json` | 直链队列 / 浏览器队列 |
| `download_results.json` | 每篇的下载结果（断点续跑依据：已 `成功` 的跳过） |
| `browser_results.json` | 浏览器下载结果与落地路径 |
| `exclusions.json` | 学科剔除清单（`non_geo_dois` / `reject_prefixes`） |
| `relevance_audit.json` | 逐篇地球科学相关性判定（`label` / `geo_hits` / `non_geo_flags` / 期刊与学科佐证） |
| `verification_report.json` | 交付复核结果：数量一致性、逐条对应、可用性、问题列表与 `match` |
| `state.json` | 当前阶段、轮次、累计成功数等汇总 |

## 8. 结束前的三关复核（不得跳过）

| 关卡 | 脚本 | 判据 |
| --- | --- | --- |
| 领域 | `audit_relevance.py` | 逐篇正文 + 期刊 + 学科字段判定；`non-geoscience` 剔除，`review` 需人工确认 |
| 数值 | `verify_deliverables.py` | `literature/` 文件数 = 清单记录数 = 成功记录数；不突破 80 篇上限 |
| 对应 | `verify_deliverables.py` | 清单每行都有文件、每个文件都被清单认领且只认领一次、无缺失/多余/重复认领 |
| 可用 | `verify_deliverables.py` | 逐篇重新打开解析：可读、≥1 页、可提取正文文本（非扫描/非空白/非摘要页） |

数量或对应关系不一致时，`verify_deliverables.py` **以非 0 退出码失败**，必须先重跑 `finalize_literature.py` 与 `build_tables.py` 再复核；仍不一致必须如实逐条报告差异，禁止虚构或重复计数。

**断点重启**：所有脚本都从这些文件读状态，`download_pdfs.py` 只处理尚未 `成功` 的条目；重跑同一命令即可续跑，不会重复下载或覆盖已有 PDF。

## 7. 审计要点（每轮必记）

- 检索词生成与被剔除的方法论词（`1_topic_analysis`）；
- **累计检索词数 ≤ 6**：超限时记 `cap_applied`；
- 每轮：浏览/重新下载条目数、新增成功数、累计成功数、是否满足数量条件（`round{N}_report.md`）；
- **累计成功达到 80 篇**（上限）即记 `hard_stop`，并立刻结束获取流程（不再检索、不再下载，直接收尾复核汇报）；
- 失败状态分布与人机验证链接清单（`manual_download_needed.md`）。
