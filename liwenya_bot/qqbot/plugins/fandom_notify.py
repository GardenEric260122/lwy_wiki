"""fandom_notify · Fandom Wiki 最近变更提醒插件

每隔 FANDOM_POLL_INTERVAL 秒轮询 Special:RecentChanges，
把新变更用李文亚口吻推送到指定群。不需要登录，直接调公开 MediaWiki API。

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

# 启动时用当前时间初始化，避免把历史记录全量推送
_last_ts: str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rc_url(title: str) -> str:
    return f"https://wenyaverse.fandom.com/zh/wiki/{title.replace(' ', '_')}"


def _format_change(rc: dict) -> str:
    """把一条 recentchanges 条目转成推送文本。"""
    title = rc.get("title", "?")
    user = rc.get("user", "?")
    comment = rc.get("comment", "").strip()
    tag = "新建" if rc.get("type") == "new" else "编辑"
    comment_part = f"（{comment}）" if comment else ""
    return f"[{tag}] 《{title}》← {user}{comment_part}\n{_rc_url(title)}"


@scheduler.scheduled_job("interval", seconds=_POLL_INTERVAL, id="fandom_rc_poll")
async def _poll_fandom_rc() -> None:
    global _last_ts
    if not _NOTIFY_GROUPS:
        return  # 未配置推送群，静默跳过

    # 离线感知：没有在线 bot 就跳过本轮，避免掉线后刷 Timeout 报错
    from nonebot import get_bots
    if not get_bots():
        logger.debug("[fandom_notify] 无在线 bot，跳过本轮推送")
        return

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

    # 最多推 5 条，防刷屏
    to_push = fresh[-5:]
    omitted = len(fresh) - len(to_push)

    lines = [f"{i + 1}. {_format_change(c)}" for i, c in enumerate(to_push)]
    header = "📖 又有人动我的世界观 Wiki！哪个单位的？！"
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
