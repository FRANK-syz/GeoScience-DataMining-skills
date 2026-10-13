# GeoScience-DataMining-skills

地球科学数据挖掘所用 skill 的集合仓库。每个 skill 占一个顶层目录，彼此独立，可单独安装到 Codex 的 skills 目录（默认 `~/.codex/skills/`）后按 skill 名调用。

## Skill 一览

| 目录 | skill 名称 | 负责环节 | 状态 |
| - | - | - | - |
| [`geo-literature-download-skill/`](geo-literature-download-skill/) | `geo-literature-download-skill` | 地球科学数据线索挖掘 · 文献获取 | 已收录 |

> 新增 skill 时：在仓库根新建与 skill 同名的顶层目录，按下方约定放置文件，并在上表补一行。

## 目录结构约定

每个 skill 目录统一采用以下结构（除 `SKILL.md` 外均按需存在）：

```
<skill-name>/
  SKILL.md              # 必需：skill 定义（frontmatter 的 name / description + 正文）
  agents/openai.yaml    # 界面显示名与默认提示词
  references/           # 按需加载的详细规格
  scripts/              # 随 skill 分发的脚本
  assets/               # 随 skill 分发的数据文件
  requirements.txt      # Python 依赖
```

各 skill 的运行前提（Python 依赖、外部服务或浏览器要求等）写在该 skill 自己的 `SKILL.md` 里，安装后即可独立运行，不依赖本仓库中的其他 skill。

## 安装

复制对应 skill 目录到 Codex 的 skills 目录：

```powershell
Copy-Item "<本仓库路径>\geo-literature-download-skill" "$env:USERPROFILE\.codex\skills\" -Recurse
```

## 已收录 skill 说明

### geo-literature-download-skill

**负责环节**：地球科学数据线索挖掘中的「文献获取」环节——围绕给定主题检索、验证并下载去重后的开放获取地球科学全文，产出可追溯的检索明细表、成功清单表与本地全文。

**功能**：在 Semantic Scholar 上按有限检索词分轮检索，逐条验证并下载可读全文，经相关性复核后去重、剔除不符合要求的页面，最终产出检索明细表与成功清单表，并做交付复核。

**运行前提**：`pip install -r geo-literature-download-skill/requirements.txt`（`pypdf`、`requests`）；检索与部分站点的 JS 挑战下载需要浏览器（Computer Use 或内置浏览器）；需要网络。

详细规格见 [`geo-literature-download-skill/SKILL.md`](geo-literature-download-skill/SKILL.md) 与 [`references/`](geo-literature-download-skill/references/)。
