# 每日 Git 变更简报 · 邮件推送配置指南

用 GitHub Actions 每天生成「距上次以来」的仓库变更简报，通过 Gmail 发到你的邮箱。

## 组成

| 文件 | 作用 |
|---|---|
| `daily_briefing.py` | 读 git log/diff 生成简报（HTML + 纯文本），用 smtplib 发信。纯标准库，无依赖。 |
| `.github/workflows/daily-briefing.yml` | 每天 UTC 04:17（北京 12:17）跑脚本发信，成功后移动 `briefing-last` tag。 |

## 一、准备 Gmail 应用专用密码（app password）

1. 打开 Gmail 所属的 Google 账户，**先开启两步验证**（app password 的前提）：
   <https://myaccount.google.com/security> → 「两步验证」。
2. 生成应用专用密码：<https://myaccount.google.com/apppasswords>
   - 应用名随便填（如 `git-briefing`），生成一串 **16 位密码**（去掉空格）。
   - 这串密码只显示一次，复制保存好。它**不是**你的 Gmail 登录密码。

> 说明：微软个人 Outlook/Hotmail 已停用基础 SMTP 认证，所以发信方用 Gmail。
> Outlook 可以作为**收件方**（填进 `MAIL_TO`）没有问题。

## 二、配置 GitHub Secrets

在仓库 `Settings → Secrets and variables → Actions → New repository secret` 加三个：

| Secret 名 | 值 |
|---|---|
| `GMAIL_USER` | 你的 Gmail 地址，如 `you@gmail.com`（发信方 + SMTP 登录名） |
| `GMAIL_APP_PASSWORD` | 上一步的 16 位应用专用密码 |
| `MAIL_TO` | 收件地址，可填 Gmail 自己或 Outlook；多个用逗号分隔 |

## 三、本地先测一遍（可选但推荐）

```bash
cd my-project

# 只生成简报看效果，不发信
python3 daily_briefing.py --since HEAD~5

# 本地发信测试（临时 export，别写进文件）
export GMAIL_USER="you@gmail.com"
export GMAIL_APP_PASSWORD="你的16位应用密码"
export MAIL_TO="you@gmail.com"
python3 daily_briefing.py --send --since HEAD~5
```

收到邮件即成功。

## 四、上线

把 `daily_briefing.py` 和 `.github/workflows/daily-briefing.yml` 提交推送到 main。
到 `Actions` 页面选「每日 Git 变更简报」→ `Run workflow` 手动触发一次验证。
之后每天 UTC 04:17 自动跑。

## 增量逻辑（「距上次以来」怎么算）

- 用 git tag `briefing-last` 记录上次简报处理到的提交。
- 每次发信成功后，工作流把该 tag 移到当前 HEAD 并推回。
- 下次运行就对比 `briefing-last..HEAD`，只报增量。
- **首次运行**没有该 tag，回退到「最近 24 小时」的提交。

## 简报重心

简报**以 Wiki 内容变化为主体**，把 `wiki_dump/` 的改动按三类分组并标状态（新增/修改/删除）：

- **条目**（`wiki_dump/articles/`）——`.wiki` 文件名会解码成条目名
- **模板**（`wiki_dump/templates/`）
- **界面与样式**（`wiki_dump/mediawiki/`，含 Common.css、导航栏等）
- 另有「站点元数据」（categories.txt / siteinfo.json）单列

仓库里的脚本、工作流、机器人等**工具代码**不是关注重点，只折叠成一行汇总
（如「工具代码：修改 3、新增 1」），不铺开文件名。

建议区会根据 Wiki 变化给针对性提示：新增条目提醒按 CLAUDE.md 规范检查
信息框/分类、Common.css 变化提醒同步线上、条目删除提醒确认等。

## 已知边界

- GitHub Actions 只能看到**已 push 的提交**，看不到你本地未提交的工作区改动。
  本地直接跑脚本才会显示 `⚠ 工作区有未提交改动`。
- 定时任务可能因 GitHub 高峰排队延迟几分钟到几十分钟，属正常。
- 公开仓库若连续 60 天无活动，定时工作流会被自动禁用；你的 backup-wiki
  每日自动 commit 会持续产生活动，通常不会触发。

## 之后可加

- **LLM 分析**：把 diff 喂给 OpenAI 兼容 API，生成带风险判断和建议的简报
  （替换 `build_advice()` 那段机械规则）。需要可用的 API 凭据。
- **多渠道**：同一份简报再发 ntfy（摘要 + 链接）、QQ 群（VPS 机器人轮询）。
