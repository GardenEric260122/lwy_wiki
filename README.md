# 李文亚 Wiki (lwy_wiki)

> 李文亚教授 Fandom Wiki 的样式与资源仓库 —— 用于版本化管理
> Wiki 站点的 Custom CSS / JS 与相关静态资源。

![License](https://img.shields.io/badge/license-CC%20BY--SA%204.0-blue.svg)
![CSS Version](https://img.shields.io/badge/wiki2.css-v1.0.0-brightgreen.svg)
![Platform](https://img.shields.io/badge/platform-Fandom%20%2F%20MediaWiki-orange.svg)

---

## 📖 项目简介

本仓库用于集中管理 **文亚宇宙世界观 Wiki** 在 Fandom / MediaWiki 平台上的
自定义样式表、脚本以及相关设计资源。所有改动通过 Git 进行版本控制，
确保样式表可回滚、可追溯、可协作维护。

**在线 Wiki**：<https://wenya-universe.fandom.com>

---

## 📂 目录结构

```text
lwy_wiki/
├── README.md                 ← 本文件
├── .gitignore                ← Git 忽略规则
└── 李文亚Wiki/
    └── wiki2.css             ← 桌面端全局基础样式表 (v1.0.0)
```

> 后续会陆续加入：
> - `wiki-mobile.css` —— 移动端样式
> - `common.js` —— 站点级脚本增强
> - `assets/` —— 图标、字体、SVG 素材

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
code 李文亚Wiki/wiki2.css
```

### 3. 快速核对线上版本号

在浏览器 DevTools Console 输入：

```js
getComputedStyle(document.documentElement).getPropertyValue('--wy-css-version')
// → "1.0.0"
```

---

## 🎨 样式覆盖范围（`wiki2.css` v1.0.0）

| 模块 | 说明 |
|------|------|
| **Design Tokens** | 统一色板 / 圆角 / 阴影变量 |
| **全局排版** | 正文字体、行高、H2/H3 标题装饰 |
| **链接交互** | 悬停下划线动画 |
| **Portable Infobox** | Fandom 信息框重构（渐变标题 + 卡片阴影）|
| **Wikitable** | 表格美化、隔行变色、悬停高亮 |
| **Table of Contents** | 目录栏卡片化样式 |

---

## 🔖 版本历史

遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/) 规范。
完整变更记录见 CSS 文件顶部 `Changelog` 注释块。

| 版本 | 日期 | 摘要 |
|------|------|------|
| **v1.0.0** | 2026-07-25 | 初始版本发布 — 全局排版 + Infobox + Wikitable + TOC |

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

```bash
# 1) 同步更新 3 处版本号：
#    - wiki2.css 顶部 Banner
#    - wiki2.css Changelog 条目
#    - :root { --wy-css-version: "x.y.z"; }

# 2) 提交并打 tag
git add -A
git commit -m "chore: bump wiki2.css to vX.Y.Z"
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push && git push --tags
```

---

## 📄 许可协议

本仓库内容采用 **[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.zh)** 协议发布，与 Fandom 平台内容协议保持一致。

---

## 👤 维护者

- **作者**：逸風（[@GardenEric260122](https://github.com/GardenEric260122)）
- **邮箱**：<jmxw0814@gmail.com>
- **反馈**：欢迎提 [Issue](https://github.com/GardenEric260122/lwy_wiki/issues) 或 PR
