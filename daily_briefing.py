"""每日 Git 变更简报：读取「距上次简报以来」的改动，生成简报并（可选）邮件推送。

用法::

    # 本地：只生成简报，打印到终端 + 写文件，不发信
    python3 daily_briefing.py

    # 本地：生成并发信（需先 export 下面的环境变量）
    python3 daily_briefing.py --send

    # 指定对比区间（覆盖默认的「上次 tag → HEAD」逻辑）
    python3 daily_briefing.py --since HEAD~5
    python3 daily_briefing.py --since 2026-08-01

设计要点：
- 「距上次以来」用 git tag `briefing-last` 标记上次简报处理到的 commit。
  首次运行（无该 tag）回退到「最近 24 小时」的提交。
  发信成功后由 CI（或加 --move-tag）把 tag 移到当前 HEAD。
- 纯标准库实现，无第三方依赖：git 用 subprocess，发信用 smtplib。
  本地（Python 3.14）和 GitHub Actions（ubuntu + setup-python）都能直接跑。
- 发信走 Gmail SSL（smtp.gmail.com:465），凭据全部从环境变量读，不落仓库。

发信所需环境变量：
    GMAIL_USER            发信 Gmail 地址（也是 SMTP 登录名）
    GMAIL_APP_PASSWORD    Gmail 应用专用密码（16 位，需先开两步验证）
    MAIL_TO               收件地址（可与 GMAIL_USER 相同；多个用逗号分隔）
    MAIL_FROM_NAME        可选，发件人显示名，默认 "Git 简报"
"""
from __future__ import annotations

import argparse
import html
import os
import smtplib
import subprocess
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

LAST_TAG = "briefing-last"
# 无 tag 时的回退窗口：抓最近这么多小时的提交
FALLBACK_HOURS = 24


# core.quotepath=false：让中文文件名原样输出，不转成八进制转义
_GIT_BASE = ["git", "-c", "core.quotepath=false"]


def run_git(*args: str) -> str:
    """跑 git 命令，返回 stdout（strip 尾部换行）。失败抛异常。"""
    result = subprocess.run(
        [*_GIT_BASE, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.rstrip("\n")


def git_ok(*args: str) -> bool:
    """跑 git 命令，只关心是否成功（用于探测 tag/ref 是否存在）。"""
    return subprocess.run(
        [*_GIT_BASE, *args],
        capture_output=True,
        text=True,
    ).returncode == 0


def resolve_range(since: str | None) -> tuple[str | None, str, str]:
    """确定简报的对比区间。

    返回 (base_ref, head_ref, human_desc)：
    - base_ref 为 None 表示「用时间窗口」（无起点 commit）。
    - head_ref 恒为当前 HEAD。
    """
    head = run_git("rev-parse", "HEAD")

    if since:
        return since, head, f"{since} → HEAD"

    # 优先用上次简报 tag 作为起点
    if git_ok("rev-parse", "--verify", f"{LAST_TAG}^{{commit}}"):
        base = run_git("rev-parse", f"{LAST_TAG}")
        if base == head:
            return base, head, "自上次简报以来无新提交"
        return base, head, f"{LAST_TAG} → HEAD"

    # 首次运行：回退到时间窗口
    return None, head, f"最近 {FALLBACK_HOURS} 小时"


def collect_commits(base: str | None, head: str) -> list[dict]:
    """收集区间内的提交信息。base 为 None 时用时间窗口。"""
    fmt = "%H%x1f%h%x1f%an%x1f%ad%x1f%s"
    if base is None:
        raw = run_git(
            "log",
            f"--since={FALLBACK_HOURS} hours ago",
            f"--pretty=format:{fmt}",
            "--date=format:%Y-%m-%d %H:%M",
        )
    else:
        if base == head:
            return []
        raw = run_git(
            "log",
            f"{base}..{head}",
            f"--pretty=format:{fmt}",
            "--date=format:%Y-%m-%d %H:%M",
        )

    commits = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        full, short, author, date, subject = line.split("\x1f")
        commits.append(
            {
                "full": full,
                "short": short,
                "author": author,
                "date": date,
                "subject": subject,
            }
        )
    return commits


# git status 字母 → 中文
_STATUS_CN = {"A": "新增", "M": "修改", "D": "删除", "R": "重命名", "C": "复制"}

# wiki_dump 各子路径 → 简报里的分组标题
_WIKI_GROUPS = [
    ("wiki_dump/articles/", "条目"),
    ("wiki_dump/templates/", "模板"),
    ("wiki_dump/mediawiki/", "界面与样式"),
]


def _pretty_wiki_name(path: str, prefix: str) -> str:
    """把 wiki_dump 里的文件路径转成可读名。

    articles/艾路迪克教授.wiki → 艾路迪克教授
    mediawiki/Common.css       → Common.css
    """
    name = path[len(prefix):]
    if name.endswith(".wiki"):
        name = name[: -len(".wiki")]
    return name


def collect_changes(base: str | None, head: str, commits: list[dict]) -> dict:
    """收集变更并按「Wiki 内容 vs 工具代码」分类。

    返回 dict：
      wiki:  {分组标题: [(状态中文, 可读名), ...]}  —— 简报主体
      tool:  {"新增": n, "修改": n, "删除": n}       —— 工具代码折叠计数
      meta:  [(状态中文, 文件名), ...]                —— 站点元数据
      total: 真实变更文件总数
    """
    empty = {"wiki": {}, "tool": {}, "meta": [], "total": 0}
    if base is None:
        if not commits:
            return empty
        # 时间窗口模式：用最早那条提交的父作为起点
        oldest = commits[-1]["full"]
        if not git_ok("rev-parse", "--verify", f"{oldest}^"):
            base = run_git("rev-list", "--max-parents=0", "HEAD")  # 根提交
        else:
            base = f"{oldest}^"

    if base == head:
        return empty

    raw = run_git("diff", "--name-status", f"{base}..{head}")

    wiki: dict[str, list[tuple[str, str]]] = {}
    tool: dict[str, int] = {}
    meta: list[tuple[str, str]] = []
    total = 0

    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0][0]  # R100 → R
        status = _STATUS_CN.get(code, code)
        # 重命名/复制有两个路径，取目标路径
        path = parts[-1]
        total += 1

        # Wiki 内容分组
        matched = False
        for prefix, group in _WIKI_GROUPS:
            if path.startswith(prefix):
                wiki.setdefault(group, []).append((status, _pretty_wiki_name(path, prefix)))
                matched = True
                break
        if matched:
            continue

        # 站点元数据
        if path in ("wiki_dump/categories.txt", "wiki_dump/siteinfo.json"):
            meta.append((status, path[len("wiki_dump/"):]))
            continue

        # 其余都算工具代码，只折叠计数
        tool[status] = tool.get(status, 0) + 1

    return {"wiki": wiki, "tool": tool, "meta": meta, "total": total}


def summarize_range(base: str | None, head: str) -> str:
    """ahead/behind 与远程对比（若有 upstream）。"""
    if not git_ok("rev-parse", "--abbrev-ref", "@{u}"):
        return ""
    counts = run_git("rev-list", "--left-right", "--count", "HEAD...@{u}")
    ahead, behind = counts.split()
    parts = []
    if int(ahead):
        parts.append(f"本地领先远程 {ahead} 个提交")
    if int(behind):
        parts.append(f"落后远程 {behind} 个提交")
    return "；".join(parts) if parts else "与远程同步"


def build_report(since: str | None) -> dict:
    """组装简报数据。"""
    branch = run_git("rev-parse", "--abbrev-ref", "HEAD")
    base, head, desc = resolve_range(since)
    commits = collect_commits(base, head)
    changes = collect_changes(base, head, commits)
    remote_state = summarize_range(base, head)

    # 工作区未提交改动（本地运行时有意义；CI 上通常为空）
    dirty = run_git("status", "--porcelain")
    dirty_files = [ln for ln in dirty.splitlines() if ln.strip()]

    # Wiki 内容变化条数（用于标题和建议）
    wiki_count = sum(len(v) for v in changes["wiki"].values())

    return {
        "generated_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "branch": branch,
        "range_desc": desc,
        "commits": commits,
        "wiki": changes["wiki"],
        "wiki_count": wiki_count,
        "tool": changes["tool"],
        "meta": changes["meta"],
        "total": changes["total"],
        "remote_state": remote_state,
        "dirty_files": dirty_files,
        "head": head,
    }


def _is_backup_only(commits: list[dict]) -> bool:
    """判断这批提交是否全是 wiki_dump 自动备份（用于给建议）。"""
    return bool(commits) and all("chore(backup)" in c["subject"] for c in commits)


def _tool_summary(tool: dict) -> str:
    """把工具代码变更折叠成一句，如「工具代码：修改 3、新增 1」。"""
    if not tool:
        return ""
    parts = [f"{status} {n}" for status, n in tool.items()]
    return "工具代码：" + "、".join(parts) + "（脚本/工作流等，非 Wiki 内容）"


def render_text(r: dict) -> str:
    """纯文本版简报（终端 + 邮件 fallback）。以 Wiki 内容变化为主体。"""
    lines = []
    lines.append(f"Wiki 变更简报 · {r['branch']} 分支")
    lines.append(f"生成时间：{r['generated_at']}")
    lines.append(f"对比区间：{r['range_desc']}")
    if r["remote_state"]:
        lines.append(f"远程状态：{r['remote_state']}")
    lines.append("")

    # ── 主体：Wiki 内容变化 ──
    if r["wiki_count"]:
        lines.append(f"【Wiki 内容变化】共 {r['wiki_count']} 处")
        for group, items in r["wiki"].items():
            lines.append(f"  {group}（{len(items)}）：")
            for status, name in items:
                lines.append(f"    [{status}] {name}")
        lines.append("")
    else:
        lines.append("【Wiki 内容变化】本区间无条目/模板/界面改动。")
        lines.append("")

    # 站点元数据
    if r["meta"]:
        lines.append("站点元数据：")
        for status, name in r["meta"]:
            lines.append(f"    [{status}] {name}")
        lines.append("")

    # ── 提交概览 ──
    if r["commits"]:
        lines.append(f"提交概览（{len(r['commits'])} 条）：")
        for c in r["commits"]:
            lines.append(f"  {c['short']}  {c['date']}  {c['author']}  {c['subject']}")
        lines.append("")

    # ── 工具代码（折叠一行）──
    tool_line = _tool_summary(r["tool"])
    if tool_line:
        lines.append(tool_line)
        lines.append("")

    if r["dirty_files"]:
        lines.append(f"⚠ 工作区有 {len(r['dirty_files'])} 处未提交改动：")
        for f in r["dirty_files"]:
            lines.append(f"  {f}")
        lines.append("")

    advice = build_advice(r)
    if advice:
        lines.append("建议：")
        for a in advice:
            lines.append(f"  - {a}")

    return "\n".join(lines)


def render_html(r: dict) -> str:
    """HTML 版简报（Gmail/Outlook 富文本）。以 Wiki 内容变化为主体。"""
    e = html.escape
    # 状态 → 徽标颜色
    badge_color = {"新增": "#3f6b3f", "修改": "#8c6d3f", "删除": "#6b2737",
                   "重命名": "#1b2a41", "复制": "#1b2a41"}

    def badge(status: str) -> str:
        color = badge_color.get(status, "#6b5f4f")
        return (
            f"<span style='display:inline-block;min-width:2.6em;text-align:center;"
            f"font-size:12px;color:#fff;background:{color};border-radius:3px;"
            f"padding:1px 6px;margin-right:8px'>{e(status)}</span>"
        )

    def wiki_html() -> str:
        if not r["wiki_count"]:
            return "<p style='color:#6b5f4f'>本区间无条目/模板/界面改动。</p>"
        blocks = []
        for group, items in r["wiki"].items():
            rows = "".join(
                f"<li style='margin:3px 0'>{badge(status)}{e(name)}</li>"
                for status, name in items
            )
            blocks.append(
                f"<p style='margin:14px 0 4px'><b>{e(group)}</b> "
                f"<span style='color:#6b5f4f'>（{len(items)}）</span></p>"
                f"<ul style='margin:0;padding-left:4px;list-style:none'>{rows}</ul>"
            )
        return "".join(blocks)

    def meta_html() -> str:
        if not r["meta"]:
            return ""
        rows = "".join(
            f"<li style='margin:3px 0'>{badge(status)}<code>{e(name)}</code></li>"
            for status, name in r["meta"]
        )
        return (
            "<p style='margin:14px 0 4px'><b>站点元数据</b></p>"
            f"<ul style='margin:0;padding-left:4px;list-style:none'>{rows}</ul>"
        )

    def commits_html() -> str:
        if not r["commits"]:
            return ""
        rows = []
        for c in r["commits"]:
            rows.append(
                "<tr>"
                f"<td style='padding:3px 10px;font-family:monospace;color:#8c6d3f'>{e(c['short'])}</td>"
                f"<td style='padding:3px 10px;color:#6b5f4f;white-space:nowrap'>{e(c['date'])}</td>"
                f"<td style='padding:3px 10px;color:#6b5f4f'>{e(c['author'])}</td>"
                f"<td style='padding:3px 10px'>{e(c['subject'])}</td>"
                "</tr>"
            )
        return (
            f"<p style='margin:14px 0 4px'><b>提交概览</b> "
            f"<span style='color:#6b5f4f'>（{len(r['commits'])} 条）</span></p>"
            "<table style='border-collapse:collapse;width:100%;font-size:13px'>"
            + "".join(rows)
            + "</table>"
        )

    def tool_html() -> str:
        line = _tool_summary(r["tool"])
        if not line:
            return ""
        return f"<p style='margin:14px 0 0;color:#6b5f4f;font-size:13px'>{e(line)}</p>"

    def dirty_html() -> str:
        if not r["dirty_files"]:
            return ""
        items = "".join(f"<li><code>{e(f)}</code></li>" for f in r["dirty_files"])
        return (
            f"<p style='color:#6b2737'><b>⚠ 工作区有 {len(r['dirty_files'])} 处未提交改动</b></p>"
            f"<ul>{items}</ul>"
        )

    def advice_html() -> str:
        advice = build_advice(r)
        if not advice:
            return ""
        items = "".join(f"<li>{e(a)}</li>" for a in advice)
        return f"<p><b>建议</b></p><ul>{items}</ul>"

    remote = (
        f"<span style='color:#6b5f4f'> · {e(r['remote_state'])}</span>"
        if r["remote_state"]
        else ""
    )
    wiki_heading = (
        f"Wiki 内容变化 <span style='color:#6b5f4f;font-weight:normal'>"
        f"（{r['wiki_count']} 处）</span>"
        if r["wiki_count"]
        else "Wiki 内容变化"
    )

    return f"""<!DOCTYPE html>
<html lang="zh"><body style="margin:0;padding:20px;background:#f7f1e4;font-family:-apple-system,'PingFang SC',sans-serif;color:#2b2621">
<div style="max-width:640px;margin:0 auto;background:#fff;border:1px solid #c9bba0;border-radius:8px;padding:24px 28px">
  <h2 style="margin:0 0 4px;color:#1b2a41">Wiki 变更简报</h2>
  <p style="margin:0 0 16px;color:#6b5f4f;font-size:13px">
    {e(r['branch'])} 分支 · {e(r['generated_at'])}<br>
    对比区间：{e(r['range_desc'])}{remote}
  </p>
  <hr style="border:none;border-top:1px solid #eadfc8;margin:16px 0">
  <h3 style="margin:0 0 4px;color:#1b2a41">{wiki_heading}</h3>
  {wiki_html()}
  {meta_html()}
  <hr style="border:none;border-top:1px solid #eadfc8;margin:16px 0">
  {commits_html()}
  {tool_html()}
  {dirty_html()}
  {advice_html()}
</div>
</body></html>"""


def build_advice(r: dict) -> list[str]:
    """基于机械规则给几条建议（LLM 版之前的占位）。"""
    advice = []
    if not r["commits"] and not r["dirty_files"]:
        return advice

    wiki = r["wiki"]
    # 新建条目提示补分类/信息框
    new_articles = [name for status, name in wiki.get("条目", []) if status == "新增"]
    if new_articles:
        preview = "、".join(new_articles[:3]) + ("…" if len(new_articles) > 3 else "")
        advice.append(
            f"新增条目 {len(new_articles)} 篇（{preview}）——"
            "按 CLAUDE.md 规范检查是否已加信息框、开篇加粗定义句和 [[分类:…]]。"
        )
    # 条目删除值得留意
    del_articles = [name for status, name in wiki.get("条目", []) if status == "删除"]
    if del_articles:
        advice.append(f"有 {len(del_articles)} 篇条目被删除，确认是否预期。")
    # 界面/样式改动
    if wiki.get("界面与样式"):
        names = [n for _, n in wiki["界面与样式"]]
        if any("Common.css" in n for n in names):
            advice.append("Common.css 有变化——如需同步线上记得走 sync_css_to_wiki.py（需管理员权限）。")
    if not r["wiki_count"] and _is_backup_only(r["commits"]):
        advice.append("本区间仅有自动备份提交，但 Wiki 内容无实质改动。")

    if r["dirty_files"]:
        advice.append(
            "工作区有未提交改动，GitHub Actions 上的简报看不到这些——如需纳入先 commit & push。"
        )
    if r["remote_state"] and "落后" in r["remote_state"]:
        advice.append("本地落后远程，建议 git pull 同步后再工作。")
    return advice


def send_email(subject: str, text_body: str, html_body: str) -> None:
    """通过 Gmail SSL 发信。凭据从环境变量读。"""
    user = os.environ.get("GMAIL_USER", "").strip()
    app_pw = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    mail_to = os.environ.get("MAIL_TO", "").strip() or user
    from_name = os.environ.get("MAIL_FROM_NAME", "Git 简报").strip()

    missing = [
        name
        for name, val in (
            ("GMAIL_USER", user),
            ("GMAIL_APP_PASSWORD", app_pw),
        )
        if not val
    ]
    if missing:
        raise SystemExit(
            "缺少发信环境变量：" + ", ".join(missing) + "\n"
            "请先 export GMAIL_USER / GMAIL_APP_PASSWORD（应用专用密码），可选 MAIL_TO。"
        )

    recipients = [addr.strip() for addr in mail_to.split(",") if addr.strip()]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, user))
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(user, app_pw)
        server.sendmail(user, recipients, msg.as_string())
    print(f"✅ 已发信给：{', '.join(recipients)}")


def move_tag(head: str) -> None:
    """把 briefing-last tag 移到当前 HEAD（本地；CI 里单独 push）。"""
    subprocess.run(["git", "tag", "-f", LAST_TAG, head], check=True)
    print(f"✅ 已更新本地 tag {LAST_TAG} → {head[:12]}（记得 git push --tags）")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 Git 变更简报并可选邮件推送")
    parser.add_argument("--send", action="store_true", help="生成后通过 Gmail 发信")
    parser.add_argument("--since", help="覆盖对比起点（commit/ref/日期），默认用 briefing-last tag")
    parser.add_argument("--move-tag", action="store_true", help="生成后把 briefing-last 移到 HEAD")
    parser.add_argument("--out-html", help="把 HTML 简报写到指定文件")
    args = parser.parse_args()

    if not git_ok("rev-parse", "--git-dir"):
        raise SystemExit("当前目录不是 git 仓库。")

    report = build_report(args.since)
    text_body = render_text(report)
    html_body = render_html(report)

    print(text_body)
    print()

    if args.out_html:
        with open(args.out_html, "w", encoding="utf-8") as f:
            f.write(html_body)
        print(f"HTML 简报已写入 {args.out_html}")

    subject_date = datetime.now().strftime("%Y-%m-%d")
    wc = report["wiki_count"]
    if wc:
        subject = f"[Wiki 简报] {subject_date} · {wc} 处内容变化"
    else:
        subject = f"[Wiki 简报] {subject_date} · 无内容变化"

    if args.send:
        send_email(subject, text_body, html_body)

    if args.move_tag:
        move_tag(report["head"])


if __name__ == "__main__":
    main()
