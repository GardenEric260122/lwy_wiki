"""fandom_notify · Fandom Wiki 最近变更提醒插件

每隔 FANDOM_POLL_INTERVAL 秒轮询 Special:RecentChanges，
把新变更推送到指定群。不需要登录，直接调公开 MediaWiki API。

配置（在 .env 里追加）：
    FANDOM_NOTIFY_GROUPS=["群号1","群号2"]   必填，接收通知的群 QQ 号列表
    FANDOM_POLL_INTERVAL=300                 可选，轮询间隔秒，默认 300（5 分钟）
    FANDOM_WIKI_API=https://...              可选，MediaWiki API 地址
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import httpx
from nonebot import get_bot, logger, require

# 同 liwenya_chat：显式加载 .env 确保自定义变量进入 os.environ
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

# ---- 配置 ----
_NOTIFY_GROUPS: list[str] = json.loads(
    os.environ.get("FANDOM_NOTIFY_GROUPS", "[]")
)
_POLL_INTERVAL: int = int(os.environ.get("FANDOM_POLL_INTERVAL", "300"))
_WIKI_API: str = os.environ.get(
    "FANDOM_WIKI_API",
    "https://wenyaverse.fandom.com/zh/api.php",
)
# 默认不带裸链接推送：QQ 对短时间内连发外部链接风控敏感，尤其是同一域名连发多条。
# 需要链接时改为 true（自担风控风险）。
_INCLUDE_LINKS: bool = os.environ.get("FANDOM_INCLUDE_LINKS", "false").lower() == "true"

# 启动时用当前时间初始化，避免把历史记录全量推送
_last_ts: str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# 离线状态标记，避免每轮都刷同一句日志；仅在状态变化时输出一次
_was_offline: bool = False


def _mark_offline(reason: str) -> None:
    global _was_offline
    if not _was_offline:
        logger.warning(f"[fandom_notify] 检测到离线，暂停推送直至恢复：{reason}")
        _was_offline = True
    else:
        logger.debug(f"[fandom_notify] 仍处于离线，跳过本轮：{reason}")


def _mark_online() -> None:
    global _was_offline
    if _was_offline:
        logger.info("[fandom_notify] 已恢复在线，继续推送")
        _was_offline = False


def _rc_url(title: str) -> str:
    return f"https://wenyaverse.fandom.com/zh/wiki/{title.replace(' ', '_')}"


def _dedup_by_title(changes: list[dict]) -> list[dict]:
    """同一页面短时间内被连续编辑多次时，只保留最新一条，避免同一链接连发。"""
    latest_by_title: dict[str, dict] = {}
    order: list[str] = []
    for rc in changes:
        title = rc.get("title", "?")
        if title not in latest_by_title:
            order.append(title)
        latest_by_title[title] = rc  # 保留该标题最新一次
    return [latest_by_title[t] for t in order]


def _format_change(rc: dict) -> str:
    """把一条 recentchanges 条目转成推送文本。默认不带裸链接，防止连续发链接触发风控。"""
    title = rc.get("title", "?")
    user = rc.get("user", "?")
    comment = rc.get("comment", "").strip()
    tag = "新建" if rc.get("type") == "new" else "编辑"
    comment_part = f"（{comment}）" if comment else ""
    line = f"[{tag}] 《{title}》← {user}{comment_part}"
    if _INCLUDE_LINKS:
        line += f"\n{_rc_url(title)}"
    return line


@scheduler.scheduled_job("interval", seconds=_POLL_INTERVAL, id="fandom_rc_poll")
async def _poll_fandom_rc() -> None:
    global _last_ts
    if not _NOTIFY_GROUPS:
        return  # 未配置推送群，静默跳过

    # 离线感知：先看有没有 WS 会话，再用 get_status 确认 QQ 账号真的在线
    # （NapCat↔NoneBot 的 WS 连接存在，不代表 QQ 账号没被腾讯踢下线）
    from nonebot import get_bots
    bots = get_bots()
    if not bots:
        _mark_offline("无在线 bot（WS 会话都不存在）")
        return

    bot_for_check = next(iter(bots.values()))
    try:
        status = await bot_for_check.get_status()
    except Exception as e:  # noqa: BLE001
        _mark_offline(f"get_status 调用失败：{e}")
        return
    if not status.get("online", False):
        _mark_offline("QQ 账号已离线（get_status.online=False）")
        return

    _mark_online()

    params = {
        "action": "query",
        "list": "recentchanges",
        "rcprop": "title|timestamp|user|comment|type",
        "rctype": "edit|new",
        "rclimit": "20",
        "rcdir": "newer",
        "rcstart": _last_ts,
        "format": "json",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_WIKI_API, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fandom_notify] 轮询 API 失败：{e}")
        return

    changes: list[dict] = data.get("query", {}).get("recentchanges", [])
    if not changes:
        return

    # 只推比 _last_ts 更新的条目（API 返回时间升序，用字符串比较 ISO 8601 安全）
    fresh = [c for c in changes if c["timestamp"] > _last_ts]

    if not fresh:
        # 没有新变更，但也要滑动时间戳到最新，避免下次重复拉旧的
        _last_ts = changes[-1]["timestamp"]
        return

    # 同一页面短时间内连续编辑多次时合并为一条，避免重复内容连发
    deduped = _dedup_by_title(fresh)

    # 最多推 5 条，防刷屏
    to_push = deduped[-5:]
    omitted = len(deduped) - len(to_push)

    lines = [f"{i + 1}. {_format_change(c)}" for i, c in enumerate(to_push)]
    header = "📖 Wiki 有新变更："
    footer = f"\n……还有 {omitted} 条，进 Wiki 自己看。" if omitted > 0 else ""
    msg = header + "\n\n" + "\n\n".join(lines) + footer

    try:
        bot = get_bot()
        for group_id in _NOTIFY_GROUPS:
            await bot.send_group_msg(group_id=int(group_id), message=msg)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[fandom_notify] 推送消息失败：{e}")
        return  # 推送失败，不滑动时间戳，下轮重试

    # 推送成功，滑动到最新时间戳
    _last_ts = fresh[-1]["timestamp"]
