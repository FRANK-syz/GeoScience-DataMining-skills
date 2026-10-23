# 流水线实现与文件契约

## 目录约定（缺失则创建）

- `breakpoint/` — 全部中间数据与审计 JSON（支持断点重启）。
- `scripts/` — 全部脚本。
- `literature/` — 文献元数据与可获取的 PDF。
- `output/` — 全部交付物（表格与 md）。

## 输入

- 数据线索 CSV（列通常为 `数据ID`,`数据名称`,`获取状态`）。**编码常为 GB2312**，读取时按 `utf-8-sig → gb2312 → gb18030 → utf-8` 顺序尝试。
- `地球科学分类.xlsx` 与 `地球科学分类-zh.xlsx`（GCMD，各含六张工作表：sciencekeywords / platforms / instruments / locations / temporalresolutionrange / horizontalresolutionrange）。前两行为表头/版本行，数据从第 3 行起，中英按行号一一对应。
- 输出文件名中的 `<原文件名>` = 输入 CSV 的 stem。

## 单条记录的 schema（`breakpoint/labelled_batch_<批次>.json`，权威数据源）

```json
{
  "name": "数据库名（须与输入表 数据名称 完全一致）",
  "portal_name": "", "home_url": "", "download_url": "", "org": "", "country": "",
  "level": "数据库级别（中文标签）",
  "science_topic": ["英文标准值"], "science_term": ["英文标准值"],
  "platform_basis": ["英文标准值"], "platform_category": ["英文标准值"],
  "instrument_category": ["英文标准值"], "instrument_class": ["英文标准值"], "instrument_type": ["英文标准值"],
  "location": "研究区域（locations 标准值，或实际区域名）",
  "gcmd_conf": "存在官方GCMD标签|根据资料推理|难以取证",
  "citations": "整数（字符串）", "citation_source": "", "cited_paper": "高被引文献标题",
  "time_coverage": "静态|2-5年|5-10年|10-20年|20-50年|50年以上|未知",
  "data_dim": "一维|二维|三维|四维|零维|未知",
  "time_uniqueness": "I0|I1|I2", "site_uniqueness": "I0|I1|I2", "rarity": "I0|I1|I2",
  "processing": "L0 原始观测数据, L3 网格分析数据",
  "funding_source": "", "funding_country": "", "funding_evidence": "官网原文",
  "access": "免费公开|注册公开|限制获取|封锁获取",
  "accessibility": "正常访问|替代访问|限制访问",
  "evidence_urls": ["https://..."], "notes": ""
}
```

要点：GCMD 数组填**英文标准值**（多值用数组），编译时映射为中文；`level`/`time_coverage`/`data_dim`/`processing`/`access`/`accessibility`/`gcmd_conf` 填**中文标签**；`citations` 为 CrossRef 实测整数（字符串）；>=4 个 Topic 时 `science_topic`/`science_term` 数组用单元素 `["综合"]`。

## 脚本与 I/O 契约（均支持 `--root <工作目录>`，默认当前目录）

| 脚本 | 输入 | 输出 |
|-|-|-|
| `build_taxonomy.py` | `地球科学分类.xlsx`、`地球科学分类-zh.xlsx` | `breakpoint/taxonomy_bundle.json` |
| `labeller_compile.py` | `breakpoint/labelled_batch_*.json`、输入 CSV | `output/labelled_<stem>.csv`、`output/label_statistic.csv` |
| `score.py` | `output/labelled_<stem>.csv` | `breakpoint/score_audit.json` |
| `write_reports.py` | `breakpoint/score_audit.json` | `output/labelled_<stem>_score.csv`、`output/Quick_report.csv` |
| `verify.py` | taxonomy bundle、labelled csv、score csv | `breakpoint/superviser_audit.json` |
| `warning_skeleton.py` | `breakpoint/superviser_audit.json`、output csv | `output/Warning.md`（骨架，叙述待补） |
| `make_audit.py` | breakpoint 全部 JSON | `breakpoint/audit.json` |
| `patch_field.py` | `breakpoint/labelled_batch_all.json` | 就地修改某条某字段（可附 note） |

首次运行时把各批次 JSON 合并为 `breakpoint/labelled_batch_all.json`（或直接以该文件名写入权威记录）；`labeller_compile.py` 会汇总所有 `labelled_batch_*.json`。

## 交付物

| 文件 | 说明 |
|-|-|
| `output/labelled_<stem>.csv` | 打标表，30 列，UTF-8 BOM |
| `output/labelled_<stem>_score.csv` | 评分表，33 列 |
| `output/Quick_report.csv` | 优先级速判表，22 列 |
| `output/label_statistic.csv` | 领域×平台×仪器 两两共现统计 |
| `output/Warning.md` | 监管核查报告 |
| `breakpoint/audit.json` | 全流程审计记录 |

## 改动与重跑（关键不变量）

**所有行级数据只存在于 `breakpoint/labelled_batch_all.json`；绝不手改任何 output CSV。**

```powershell
python scripts/patch_field.py --root . --name "USGS NWIS (…)" --field site_uniqueness --value I0 --note "…"
python scripts/labeller_compile.py --root .
python scripts/score.py            --root .
python scripts/write_reports.py    --root .
python scripts/verify.py           --root .
python scripts/warning_skeleton.py --root .   # 复核后按真实结果补齐叙述
python scripts/make_audit.py       --root .
```

任何字段改动都可能连锁改变：不可替代性总分（`I0` 权重最高）→ 平均总分 → 优先级标签/后缀 → 分级。改完必须核对并说明**改了什么、影响哪些字段、分数/优先级是否变化**。

## 复核清单（每轮收尾执行）

1. 官网入口逐条复查（Superviser 步骤 1/9）：不可达者找同源替代页或 Wayback 并记入证据，可访问性不得填“正常访问”。
2. 字段口径一致性复核：对需要登录/注册的条目统一“数据获取条件”口径（`注册公开`）；对地下/深部、海底/深海、高山/极地观测统一“场地唯一性”口径（`I0`）。
3. 边界复核：被引恰为阈值的条目、分级阈值边界条目（如数据价值总分=90.0 落 Tier1）。
4. 运行 `verify.py` 确认：GCMD 越界 0、大类留空 0、分隔符异常 0、复算不一致 0、列结构正常。
