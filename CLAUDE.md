# CLAUDE.md — 文亚宇宙世界观 Wiki 项目

本文件供 Claude Code 快速理解本项目。撰写 Wiki、改样式、跑脚本前请先读此文件。

## 项目是什么

本仓库管理 **文亚宇宙世界观 Wiki**（<https://wenyaverse.fandom.com/zh>，Fandom/MediaWiki 平台）的：
- **桌面样式表**：`styles/common.css`（部署到线上 `MediaWiki:Common.css`）
- **Pywikibot 自动化脚本**：登录、抓取、批量编辑、CSS 同步等
- **内容镜像备份**：`wiki_dump/`（每日由 GitHub Actions 自动更新）

## ⚙️ 运行须知（每次跑脚本前必读）

1. **必须开启 Clash Verge 代理**（`127.0.0.1:7897`）——本地脚本经代理访问 Fandom；
   代理地址已写入 `user-config.py`，但代理软件本身要运行。（CI 环境自动跳过代理。）
2. **必须用 `.venv/bin/python`**，不要用系统 `python3`（未装 pywikibot）。
3. 运行时的 `Sleeping for X seconds` 是**正常限速保护**，非卡死；新建/批量操作请耐心等。
4. 脚本大多有 **dry-run 默认 + `--execute` 才写入** 的安全设计，先预览再执行。
5. 编辑 `MediaWiki:` 命名空间（含 Common.css）需**管理员权限**，普通机器人账号会被拒。

## 📝 Wiki 条目编写规范

基于现有 60 篇条目提炼的惯例，新条目应遵循：

### 人物条目（最常见）骨架
```
{{Character|name=…|image=….png|foreign_name=…|birth_date=…|birth_place=…|
  occupation=…|affiliation=[[…]]|position=…|fields=…|rival=[[…]]|caption=…}}
'''全名'''（外文名，生年－），一句话定义（身份、所属、研究方向）。

== 生平 ==
== 学术/研究经历 ==
== 研究成果 ==   （可用 === 子章节 === 分列各成果，每项以 '''加粗名''' 开头）
== 争议 ==       （如有）
== 评价 ==       （支持者认为…／批评者则认为…，保持双方视角）
== 相关条目 ==   （* [[…]] 列表，几乎每篇必有）

[[分类:李文亚宇宙人物]]
```

### 机构条目
用 `{{Institutions|...}}` 信息框（字段：founded/founder/location/director/
type/fields/departments/projects/achievements/controversy/evaluation/status/members…）。
骨架：机构概况 → 发展历程 → 主要争议 → 评价 → 相关条目。分类 `[[分类:李文亚宇宙机构]]`。

### 理论/学说条目
用 `{{Theory|...}}` 信息框（字段：foreign_name/proposer/proposed_date/field/
core_claim/key_concepts/related_theories/status）。
骨架：加粗定义句 → 内容 → 相关条目。分类 `[[分类:李文亚宇宙理论]]`。
```
{{Theory|name=…|proposer=[[李文亚]]|field=…|core_claim=…|status=争议理论}}
'''理论名'''是[[李文亚]]提出的……。
== 内容 ==
== 相关条目 ==
[[分类:李文亚宇宙理论]]
```

### 通用规则
- **开篇必有加粗定义句**：`'''条目名'''（外文名，…），…`（仿维基百科体例）。
- **命名一致**：人物条目统一用「XX教授」形式；引用时保持写法一致（避免分裂红链，
  详见线上 [机器人操作日志](https://wenyaverse.fandom.com/zh/wiki/Project:机器人操作日志)）。
- **务必加分类**：`[[分类:…]]`（中文命名空间，不要用 `Category:`）。现有分类见
  `wiki_dump/categories.txt`；人物→`李文亚宇宙人物`，机构→`李文亚宇宙机构`。
- **语气**：百科式中立叙述外壳（「据称」「支持者认为」），题材为围绕「李文亚」的戏仿叙事。
- 大量内部链接 `[[…]]` 构成条目互联网络。

### 可用模板
条目里实际用得最多的是信息框；大量实用模板存在但曾长期未被使用，撰写时应主动用起来。
- 信息框：`{{Character}}`（人物）、`{{Institutions}}`（机构）、`{{Theory}}`（理论）、`{{Event}}`（事件）
- 维护提示：`{{维护提示|title=…|text=…|icon=⚠️}}` —— 对应 `common.css` 的 `.wy-maintenance` 样式
- 小作品：`{{Stub}}` —— 内容简短、结构不全的条目挂在页尾
- 导航/引用：`{{Main|主条目}}`、`{{See_also|…}}`、`{{Further|…}}`、`{{Hatnote|…}}`、`{{Quote|…}}`、`{{Cite_web|…}}`
- 管理：`{{Delete}}`（提请删除）、`{{Disambiguation}}`（消歧义）

> 新模板源码放 `wiki_templates/`，用 `.venv/bin/python upload_templates.py <名> --execute` 上传。
> 给残缺条目挂 Stub：`.venv/bin/python tag_stubs.py --execute`。

## 🎨 CSS 版本管理

- 平时**只编辑** `styles/common.css`；历史版本在 `styles/archive/common-vX.Y.Z.css`。
- 发布：`.venv/bin/python bump_css_version.py`（分析 diff 建议级别）→ 加 `--level X --execute`。
- 同步线上：`.venv/bin/python sync_css_to_wiki.py --execute`（需管理员权限）。
- SemVer：删变量/改选择器=MAJOR，新增 class/规则=MINOR，改色值/数值=PATCH。
- CI（`css-version-check.yml`）会在改了 CSS 却没升版本号时报错。

## 🤖 脚本清单

| 脚本 | 用途 |
|------|------|
| `test_bot_connection.py` | 验证登录与账号权限 |
| `test_sandbox_edit.py [页名]` | 沙盒编辑测试 |
| `fetch_wiki_content.py` | 抓取全站内容到 `wiki_dump/` |
| `create_redirects.py [--execute]` | 批量创建重定向（幂等） |
| `publish_announcement.py [--execute]` | 发布操作公告/讨论页 |
| `bump_css_version.py [--level X --execute]` | CSS 版本发布 |
| `sync_css_to_wiki.py [--execute]` | 同步 common.css 到线上 |
| `upload_templates.py [名] [--execute]` | 上传 `wiki_templates/` 下模板到线上 |
| `tag_stubs.py [--execute]` | 给残缺条目挂 `{{Stub}}` |

## 🗂 关键路径

- 凭据 `user-password.py`（**不入库**，含明文密码，勿外传）；格式见 README。
- 每日备份工作流：`.github/workflows/backup-wiki.yml`（UTC 03:45 / 北京 11:45）。
- 镜像快照：`wiki_dump/`（`articles/` `templates/` `mediawiki/` `siteinfo.json`）。
