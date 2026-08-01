"""bilibili_notify · B站UP主最新视频提醒插件（RSSHub版）

通过本地 RSSHub 实例获取 B站 UP 主最新投稿，无需 WBI 签名和 Cookie。
RSSHub 部署：docker run -d --name rsshub --restart always -p 1200:1200 diygod/rsshub

配置（在 .env 里追加）：
    BILI_NOTIFY_GROUPS=["群号1","群号2"]    必填
    BILI_UIDS=["UID1","UID2"]               必填
    BILI_UID=xxxxxxx                         兼容旧配置（BILI_UIDS 优先）
    BILI_POLL_INTERVAL=300                   可选，轮询间隔秒，默认 300
    RSSHUB_BASE_URL=http://127.0.0.1:1200    可选，RSSHub 地址
"""
import json
import os
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from dotenv import load_dotenv
import httpx
from nonebot import get_bot, get_bots, logger, require

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

_NOTIFY_GROUPS: list[str] = json.loads(os.environ.get("BILI_NOTIFY_GROUPS", "[]"))

_raw_uids = os.environ.get("BILI_UIDS", "")
if _raw_uids:
    _UIDS: list[str] = [u.strip() for u in json.loads(_raw_uids) if str(u).strip()]
else:
    _single = os.environ.get("BILI_UID", "").strip()
    _UIDS = [_single] if _single else []

_POLL_INTERVAL: int = int(os.environ.get("BILI_POLL_INTERVAL", "300"))
_RSSHUB_BASE: str = os.environ.get("RSSHUB_BASE_URL", "http://127.0.0.1:1200").rstrip("/")

_last_bvids: dict[str, str] = {}
_was_offline: bool = False


def _mark_offline(reason: str) -> None:
    global _was_offline
    if not _was_offline:
        logger.warning(f"[bilibili_notify] 暂停推送：{reason}")
        _was_offline = True


def _mark_online() -> None:
    global _was_offline
    if _was_offline:
        logger.info("[bilibili_notify] 已恢复在线")
        _was_offline = False


async def _fetch_rss(client: httpx.AsyncClient, uid: str) -> tuple[str, list[dict]]:
    """返回 (author, [{bvid, title}, ...])，最多取前5条。"""
    resp = await client.get(f"{_RSSHUB_BASE}/bilibili/user/video/{uid}", timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    channel = root.find("channel")
    if channel is None:
        return uid, []

    author = channel.findtext("title", default=uid)
    items = []
    for item in channel.findall("item")[:5]:
        title = item.findtext("title", default="?")
        link = item.findtext("link", default="")
        m = re.search(r"(BV[a-zA-Z0-9]+)", link)
        if m:
            items.append({"bvid": m.group(1), "title": title})
    return author, items


async def _check_uid(client: httpx.AsyncClient, uid: str) -> str | None:
    try:
        author, videos = await _fetch_rss(client, uid)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[bilibili_notify] UID {uid} 拉取失败：{e}")
        return None

    if not videos:
        return None

    latest_bvid = videos[0]["bvid"]
    last = _last_bvids.get(uid)

    if not last:
        _last_bvids[uid] = latest_bvid
        return None

    if latest_bvid == last:
        return None

    new_videos = []
    for v in videos:
        if v["bvid"] == last:
            break
        new_videos.append(v)
    new_videos.reverse()

    if not new_videos:
        _last_bvids[uid] = latest_bvid
        return None

    _last_bvids[uid] = latest_bvid
    header = f"📺 {author} 发新视频了："
    lines = [f"《{v['title']}》\nhttps://www.bilibili.com/video/{v['bvid']}" for v in new_videos]
    return header + "\n\n" + "\n\n".join(lines)


@scheduler.scheduled_job("interval", seconds=_POLL_INTERVAL, id="bilibili_video_poll")
async def _poll_bilibili() -> None:
    if not _NOTIFY_GROUPS or not _UIDS:
        return

    bots = get_bots()
    if not bots:
        _mark_offline("无在线 bot")
        return

    try:
        status = await next(iter(bots.values())).get_status()
    except Exception as e:  # noqa: BLE001
        _mark_offline(f"get_status 失败：{e}")
        return
    if not status.get("online", False):
        _mark_offline("QQ 账号已离线")
        return

    _mark_online()

    messages: list[str] = []
    async with httpx.AsyncClient() as client:
        for uid in _UIDS:
            msg = await _check_uid(client, uid)
            if msg:
                messages.append(msg)

    if not messages:
        return

    try:
        bot = get_bot()
        for group_id in _NOTIFY_GROUPS:
            for msg in messages:
                await bot.send_group_msg(group_id=int(group_id), message=msg)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[bilibili_notify] 推送失败：{e}")
