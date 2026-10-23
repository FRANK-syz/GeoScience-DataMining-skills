---
name: geodatabase-rate-skill
description: Triage a table of geoscience database/dataset leads into a collection-priority list — GCMD multi-label tagging, value/sensitivity/scarcity scoring with P0–P4 priority, and an independent audit report. Use when the user supplies a CSV of geoscience data-portal leads (e.g. ModCon / 创世纪计划 数据地图, columns 数据ID/数据名称), or asks to re-run, extend, or independently audit such a labelling-scoring pipeline.
metadata:
  short-description: 地学数据库线索 打标·评分·监管三阶段
---

# Geodatabase Rate Skill (Labeller → Rater → Superviser)

Turn a CSV of geoscience database leads into three deliverables: a fully tagged table, a scored table with collection priority, and an audit report. Everything is evidence-driven — every label, score, and citation must trace to a real source.

## When this applies

- A CSV of geoscience database/dataset leads (typically `数据ID`,`数据名称`,`获取状态`). The GCMD workbooks are **optional**: this skill ships them in `assets/`, and uses a workspace copy of `地球科学分类.xlsx` / `地球科学分类-zh.xlsx` only if one is present.
- The user asks to label, score, rank, or audit such databases; or to fix a field and re-run a previous pass.

Not for: plain data cleaning/visualisation, or scoring unrelated to GCMD classification.

## Three stages

1. **Labeller** — for each row, visit the official portal, gather evidence, and assign all fields → `output/labelled_<原文件名>.csv` (+ `output/label_statistic.csv`).
2. **Rater** — score each row from the labelled table → `output/labelled_<原文件名>_score.csv` (+ `output/Quick_report.csv`).
3. **Superviser** — independently verify and report → `output/Warning.md`. Runs in parallel but must finish after the other two.

`scripts/init_workspace.py` creates `breakpoint/`, `scripts/`, `literature/`, `output/` with an audit skeleton.

## Read before you decide

- `references/prompt-contract.md` — authoritative field list, rubric tables, formulas, tier thresholds, priority rules, audit steps. **Do not score or label from memory; thresholds differ between 分级表 (`>` vs `≥`).**
- `references/pipeline.md` — folder/file contract, record schema, script I/O, deliverables, rerun order.
- `references/rubrics-and-traps.md` — judgement conventions and known pitfalls (encoding, uniqueness conventions, boundary thresholds, anti-fabrication).

## Hard constraints

- **Evidence, never fabrication.** Every field traces to an official page, official doc, or a measured lookup. Citations must be real integers, measured CrossRef-first (fallbacks: Google Scholar — **manual, no API** — and DataCite/OpenAlex via `cites.py`; take the max of the fallbacks); no estimates, no rounding, no substituting an unrelated highly-cited paper.
- **Encoding:** input CSV is usually **GB2312**; write every output as **UTF-8 with BOM** (`utf-8-sig`).
- **Multi-label separator** is exactly `", "` (English comma + space), never a bare comma.
- **≥4 Topics** ⇒ that row's Topic and Term labels become `综合`.
- **综合数据门户 exception:** rows classified as `综合数据门户` (a cross-domain discovery/navigation portal aggregating multiple databases, e.g. NASA Earthdata, NOAA NCEI) keep **only** the level label — every other field stays blank, and Rater/Superviser skip scoring and compliance checks for them. Rows are still kept (row count matches the input).
- **大类字段 (地球科学领域-领域 / 平台-基座 / 仪器-大类) must never be blank.**
- **Accessibility:** if the portal fails (403 / TLS / 404 / timeout), use an official mirror, another official page, or a Wayback snapshot — and record the substitute in evidence; it is **not** `正常访问`.
- **Never silently skip or duplicate rows** — row count must match the input lead table.
- Respect Superviser independence: it verifies, it does not re-label or re-score.

## Single source of truth

All row data lives in `breakpoint/labelled_batch_all.json`. To change any field, patch that JSON (e.g. `scripts/patch_field.py`) and **re-run the whole chain** — never hand-edit an output CSV.

## Scripts (`--root` defaults to the current directory)

| Script | Role |
|-|-|
| `init_workspace.py` | create the four folders + audit skeleton |
| `build_taxonomy.py` | `assets/` or workspace GCMD workbooks → `breakpoint/taxonomy_bundle.json` |
| `fetch_evidence.py` | snapshot official pages into `literature/` + `breakpoint/evidence_index.json` |
| `cites.py` | measured citation counts (CrossRef → DataCite → OpenAlex) |
| `labeller_compile.py` | records JSON → `output/labelled_<stem>.csv` + `label_statistic.csv` |
| `score.py` | rubric scoring → `breakpoint/score_audit.json` |
| `write_reports.py` | → `output/labelled_<stem>_score.csv` + `Quick_report.csv` |
| `verify.py` | GCMD/blanks/separator/recompute/concentration/structure → `breakpoint/superviser_audit.json` |
| `warning_skeleton.py` | → `output/Warning.md` skeleton (fill the narrative) |
| `make_audit.py` | → `breakpoint/audit.json` |
| `patch_field.py` | edit one field of one record in the source JSON |

```powershell
python scripts/build_taxonomy.py    --root .   # only when the workbook changes
python scripts/labeller_compile.py  --root .   # JSON -> labelled CSV (+ label_statistic)
python scripts/score.py             --root .   # -> breakpoint/score_audit.json
python scripts/write_reports.py     --root .   # -> score CSV + Quick_report.csv
python scripts/verify.py            --root .   # -> breakpoint/superviser_audit.json
python scripts/warning_skeleton.py  --root .   # -> Warning.md skeleton (fill the narrative)
python scripts/make_audit.py        --root .   # -> breakpoint/audit.json
```

Region re-classification (研究区域 → 国家级/大洲级/全球级/地区级) uses built-in rules; override or extend per run with `breakpoint/region_map.json` (`{"欧洲":"大洲级"}`).

## Finishing

Run `references/pipeline.md`'s review checklist (re-check unreachable portals; align 数据获取条件 and 场地唯一性 conventions; confirm boundary thresholds). Then report **per stage**:

- **Labeller** — after re-checking unlabelled rows with broader searches: counts of labelled-successful and labelled-failed rows, plus the labelled table path.
- **Rater** — the five databases with the highest 数据价值总分 and the five with the highest 敏感性总分, each with a one-line reason.
- **Superviser** — P0 names + count, P1 count, output paths, and warnings with fixes.

Whenever a field is revised, state **what changed, which downstream fields move, and whether score/priority changed**.
