# 文亚宇宙世界观 Wiki

> 文亚宇宙世界观 在Fandom上的 Wiki 的样式与资源仓库 —— 用于版本化管理
> Wiki 站点的 Custom CSS / JS 与相关静态资源。

![License](https://img.shields.io/badge/license-CC%20BY--SA%204.0-blue.svg)
![CSS Version](https://img.shields.io/badge/common.css-v2.1.0-brightgreen.svg)
![Platform](https://img.shields.io/badge/platform-Fandom%20%2F%20MediaWiki-orange.svg)

---

## 📖 项目简介

本仓库用于集中管理 **文亚宇宙世界观 Wiki** 在 Fandom / MediaWiki 平台上的
自定义样式表、**Pywikibot 自动化脚本**、内容镜像备份与分析文档。所有改动
通过 Git 进行版本控制，确保可回滚、可追溯、可协作维护。

**在线 Wiki**：<https://wenyaverse.fandom.com/zh>

---

## 📂 目录结构

```text
lwy_wiki/
├── README.md                        ← 本文件
├── .gitignore                       ← Git 忽略规则
│
├── styles/                          ← 样式表
│   ├── common.css                  ← 唯一编辑入口（当前版本，发布时归档）
│   └── archive/                    ← 历史版本快照
│       ├── common-v2.0.0.css
│       └── common-v1.0.0.css
│
├── Pywikibot 配置
│   ├── user-config.py              ← 站点/账号/代理配置
│   └── fandom_family.py            ← 手写 family 文件 (scriptpath=/zh)
│
├── 自动化脚本
│   ├── test_bot_connection.py      ← 登录与账号权限验证
│   ├── test_sandbox_edit.py        ← 沙盒编辑测试 (可传页名参数)
│   ├── fetch_wiki_content.py       ← 抓取全站内容到 wiki_dump/
│   ├── create_redirects.py         ← 批量创建重定向 (dry-run/幂等)
│   ├── publish_announcement.py     ← 发布操作公告与讨论页
│   └── bump_css_version.py         ← CSS 语义化版本发布 (diff 建议级别+归档)
│
├── 文档
│   ├── wiki内容与样式分析报告.md
│   ├── 镜像快照问题分析与改进建议.md
│   └── 公共沙盒页操作指南.md
│
├── wiki_dump/                       ← 线上内容镜像快照 (60 条目/91 模板/36 界面页)
│
├── liwenya_bot/                     ← 「李文亚」QQ 机器人（NoneBot2 + Claude API）
│   ├── liwenya_persona.txt         ← 人格 system prompt（虚构戏仿框架）
│   ├── test_once.py                ← API + 人格一次性连通测试
│   └── qqbot/                      ← NoneBot2 项目
│       ├── bot.py                  ← 入口
│       ├── DEPLOY.md               ← VPS 部署清单
│       ├── 改进指南.md              ← 后续改进 / 运维踩坑记录
│       └── plugins/                ← liwenya_chat（对话）/ fandom_notify（变更提醒）
│
└── (被 .gitignore 忽略，不入库)
    ├── user-password.py            ← BotPasswords 凭据（含明文密码）
    ├── liwenya_bot/**/.env         ← 机器人密钥（API key 等）
    ├── .venv/                      ← Python 虚拟环境
    └── throttle.ctrl               ← Pywikibot 运行时速率控制文件
```

---

## 🚀 使用方式

### 1. 部署到 Fandom Wiki

1. 登录 Fandom 后台，进入 **管理面板 → 高级设置 → 主题设计器**
2. 打开 `MediaWiki:Wikia.css`（或 `MediaWiki:Common.css`）
3. 将本仓库对应文件内容**粘贴**进去
4. 保存 → 清理浏览器缓存（Ctrl/Cmd + Shift + R）

### 2. 本地开发预览

```bash
# 克隆仓库
git clone https://github.com/GardenEric260122/lwy_wiki.git
cd lwy_wiki

# 使用任意编辑器打开 CSS 文件
code styles/common.css
```

### 3. 快速核对线上版本号

在浏览器 DevTools Console 输入：

```js
getComputedStyle(document.documentElement).getPropertyValue('--wy-css-version')
// → "2.0.0"
```

---

## 🤖 Pywikibot 自动化

本仓库纳管使用 [Pywikibot](https://www.mediawiki.org/wiki/Manual:Pywikibot/zh)
批量维护 Wiki 的完整配置与脚本，已实测可正常登录、编辑。

### 环境准备

```bash
# 1) 创建虚拟环境并安装（系统 Python 为 externally-managed，需用 venv）
python3 -m venv .venv
.venv/bin/pip install pywikibot

# 2) 确保代理开启（Fandom 需经代理访问；地址已写入 user-config.py）
#    Clash Verge 系统代理：127.0.0.1:7897
```

### 配置说明

- **`user-config.py`**（已入库）—— 指定 family/语言、注册 `fandom_family.py`、
  登录账号、浏览器式 User-Agent、Clash 代理（`127.0.0.1:7897`）、编辑速率限制。
- **`fandom_family.py`**（已入库）—— 手写 family 文件，`scriptpath` 指向 `/zh`
  （本站 API 在 `/zh/api.php`），避免 Fandom 拦截自动探测（403）。
- **`user-password.py`**（**不入库**）—— BotPasswords 凭据，Pywikibot 11 格式：

  ```python
  # ('Bot主账号用户名', BotPassword('BotPasswords名字', '高强度密码'))
  ('WenyaverseBot', BotPassword('WenyaverseBot', '<你的高强度密码>'))
  ```

  在 Fandom **Special:BotPasswords** 生成密码后填入。含明文密码，已被
  `.gitignore` 忽略，**切勿提交或外传**。

### 脚本一览

| 脚本 | 用途 |
|------|------|
| `test_bot_connection.py` | 验证登录状态与账号权限组 |
| `test_sandbox_edit.py [页名]` | 沙盒页「写入→读回」测试，验证编辑权限 |
| `fetch_wiki_content.py` | 抓取全站条目/模板/界面页/配置到 `wiki_dump/` |
| `create_redirects.py [--execute] [--limit N]` | 批量创建重定向，默认 dry-run，幂等安全 |
| `publish_announcement.py [--execute]` | 发布机器人操作公告与社区讨论页 |

### 快速开始

```bash
# 验证登录（须开着代理，用 venv 的 python）
.venv/bin/python test_bot_connection.py
```

> ⚠️ 运行须知：
> 1. **必须开启 Clash Verge 代理**（脚本读取 user-config.py 内置代理，但代理软件本身要运行）；
> 2. **用 `.venv/bin/python`**，勿用系统 `python3`（未装 pywikibot）；
> 3. 运行时出现的 `Sleeping for X seconds` 是正常限速保护，非卡死。

---

## 🤖 「李文亚」QQ 机器人

`liwenya_bot/` 是一个以**李文亚教授**风格对话的 QQ 群机器人，同时能把 Wiki
的最近变更推送到群里。它复用了本项目的 `liwenya-perspective` 人格资产与
Pywikibot 基建，是 Wiki 世界观在群聊里的延伸。

### 架构

```text
QQ ↔ NapCat（OneBot v11）↔ 反向 WebSocket ↔ NoneBot2 ↔ Claude 中转 API
```

| 层 | 选型 | 说明 |
|----|------|------|
| QQ 协议端 | **NapCat** | 非官方 NTQQ 协议端，OneBot v11 标准（⚠️ 有封号风险，务必用小号）|
| 机器人框架 | **NoneBot2**（Python） | 与现有脚本同语言，插件生态全 |
| 对话大脑 | **Claude API**（`claude-sonnet-5`，经中转）| 人格 = `liwenya_persona.txt` 作 system prompt |
| 部署 | **境外 VPS** + systemd 常驻 | 7×24；见 `qqbot/DEPLOY.md` |

### 功能

| 插件 | 触发 | 作用 |
|------|------|------|
| `liwenya_chat` | 群里 `@机器人` 或私聊 | 「文亚Bot」多轮问答/群聊辅助；`@机器人 重置` 或含「退出/不用演了」清空上下文 |
| `fandom_notify` | 定时轮询（默认 5 分钟）| 把 Wiki `Special:RecentChanges` 的新变更推到指定群 |

普通群消息不触发，仅 @ / 私聊才调 API，配合冷却与上下文轮数限制控成本。

### 本地快速验证（不需要 QQ）

```bash
# 在 liwenya_bot/.env 填好 LIWENYA_BASE_URL(带 /v1)、LIWENYA_API_KEY、LIWENYA_MODEL
.venv/bin/python liwenya_bot/test_once.py "光合作用真的需要二氧化碳吗？"
```

### 相关文档

- **部署**：[`liwenya_bot/qqbot/DEPLOY.md`](liwenya_bot/qqbot/DEPLOY.md) —— VPS 从零部署清单
- **规划**：[`QQ机器人实施方案.md`](QQ机器人实施方案.md) —— 技术选型与分阶段实施
- **改进 / 运维**：[`liwenya_bot/qqbot/改进指南.md`](liwenya_bot/qqbot/改进指南.md) —— 后续优化项与踩坑记录

> ⚠️ **密钥安全**：机器人所有密钥走 `.env`（已 gitignore，**不入库**）；
> QQ 请用专用小号，勿绑重要关系链。

---

## 🎨 样式覆盖范围（`common.css` v2.0.0+）

| 模块 | 说明 |
|------|------|
| **Design Tokens** | 统一浅色 / 深色双主题色板、圆角、阴影变量 |
| **全局排版** | 正文字体、行高、H1/H2/H3 标题装饰 |
| **深色模式适配** | 修复标题、链接、目录在深色模式下不可见问题 |
| **链接交互** | 悬停下划线动画 |
| **Portable Infobox** | Fandom 信息框重构（渐变标题 + 卡片阴影）|
| **Wikitable** | 表格美化、隔行变色、悬停高亮 |
| **Table of Contents** | 目录栏卡片化样式、修复“目录”标题过暗与白色闪光 |

---

## 🔖 版本历史

遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/) 规范。
完整变更记录见 CSS 文件顶部 `Changelog` 注释块。

| 版本 | 日期 | 摘要 |
|------|------|------|
| **v2.1.0** | 2026-07-28 | 收编线上维护提示框样式（`.wy-maintenance*`）；建立 CSS 版本控制机制 |
| **v2.0.0** | 2026-07-25 | 统一浅/深色令牌，修复深色模式可见性、目录闪光、写死背景色 |
| **v1.0.0** | 2026-07-25 | 初始版本发布 — 全局排版 + Infobox + Wikitable + TOC |

> 每个版本对应一个 git tag（`vX.Y.Z`）与 `archive/` 中的快照文件。

---

## 🧹 Wiki 维护操作记录

通过机器人对线上 Wiki 执行的自动化维护（详见线上
[机器人操作日志](https://wenyaverse.fandom.com/zh/wiki/Project:机器人操作日志)）：

| 日期 | 操作 | 说明 |
|------|------|------|
| 2026-07-27 | 重定向规范化 | 创建 6 个重定向消除「带/不带教授」分裂红链（孙笑川、卢初雪、卢德霜、侯国玉、关瑞生 → 各自「教授」页；李文亚教授 → 李文亚）|
| 2026-07-27 | 发布公告/讨论页 | 创建机器人用户页、操作日志页、社区讨论页 |

> 完整问题扫描与后续计划见 [`镜像快照问题分析与改进建议.md`](镜像快照问题分析与改进建议.md)。

---

## 🛠 开发协作规范

### Commit Message 前缀（Conventional Commits）

| 前缀 | 含义 | 示例 |
|------|------|------|
| `feat` | 新增样式 / 组件 | `feat(infobox): add role subheader style` |
| `fix` | 修复样式 bug | `fix(table): correct border radius on Safari` |
| `style` | 色值 / 间距微调 | `style: tweak toc padding` |
| `docs` | 文档改动 | `docs: update readme` |
| `refactor` | 结构重构不改外观 | `refactor: unify color tokens` |
| `chore` | 构建 / 元数据 | `chore: bump version to 1.1.0` |

### 发布新版本流程

CSS 版本发布由脚本 `bump_css_version.py` 辅助，避免漏改版本号：

```bash
# 0) 平时只编辑 styles/common.css

# 1) 预览版本建议（脚本分析 git diff，建议 major/minor/patch）
.venv/bin/python bump_css_version.py

# 2) 确认级别并写入（自动更新 3 处版本号 + 归档到 archive/）
.venv/bin/python bump_css_version.py --level <major|minor|patch> --execute

# 3) 在 common.css 顶部补写本版 Changelog 条目，然后提交并打 tag
git add styles/
git commit -m "feat(css): release common vX.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push && git push --tags

# 4) 同步线上：.venv/bin/python sync_css_to_wiki.py --execute
```

> **CI 校验**：`.github/workflows/css-version-check.yml` 会在 `common.css`
> 改动却未升版本号时让检查失败，提醒你先运行上面的脚本。

**版本级别判定（SemVer）：**

| 级别 | 触发 | 示例 |
|------|------|------|
| MAJOR | 删除/重命名 `--wy-*` 变量或改动现有选择器（破坏性）| 移除某设计令牌 |
| MINOR | 仅新增 class / 变量 / 规则（向后兼容）| 新增维护提示框样式 |
| PATCH | 仅改色值 / 数值 / 注释 | 微调间距、修 bug |

---

## 📄 许可协议

本仓库内容采用 **[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.zh)** 协议发布，与 Fandom 平台内容协议保持一致。

---

## 👤 维护者

- **作者**：逸風（[@GardenEric260122](https://github.com/GardenEric260122)）
- **邮箱**：<jmxw0814@gmail.com>
- **反馈**：欢迎提 [Issue](https://github.com/GardenEric260122/lwy_wiki/issues) 或 PR
