"""bilibili_notify · B站UP主最新视频提醒插件（动态流版）

使用 x/polymer/web-dynamic/v1/feed/space 接口，无需 WBI 签名。
国内服务器 + Cookie 设备指纹（buvid3/buvid4/b_nut）可有效避免 -352 风控。

配置（在 .env 里追加）：
    BILI_NOTIFY_GROUPS=["群号1","群号2"]    必填
    BILI_UIDS=["UID1","UID2"]               必填
    BILI_UID=xxxxxxx                         兼容旧配置（BILI_UIDS 优先）
    BILI_POLL_INTERVAL=300                   可选，轮询间隔秒，默认 300
    BILI_COOKIE=buvid3=...;buvid4=...       可选，但强烈建议填写（设备指纹，无需登录态）
    BILI_PROXY=http://127.0.0.1:7890        可选，HTTP/SOCKS5 代理，国内服务器 IP 被封时必填
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv
import httpx
from nonebot import get_bots, logger, require

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
_BILI_COOKIE: str = os.environ.get("BILI_COOKIE", "")
_BILI_PROXY: str = os.environ.get("BILI_PROXY", "")

_DYNAMIC_API = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://space.bilibili.com",
}

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


async def _fetch_videos(client: httpx.AsyncClient, uid: str) -> tuple[str, list[dict]]:
    """返回 (author_name, [{bvid, title}, ...])，只取视频动态，最多 5 条。"""
    headers = {
        **_BASE_HEADERS,
        "Referer": f"https://space.bilibili.com/{uid}/video",
    }
    if _BILI_COOKIE:
        headers["Cookie"] = _BILI_COOKIE

    resp = await client.get(
        _DYNAMIC_API,
        params={"host_mid": uid},
        headers=headers,
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()

    code = payload.get("code", -1)
    if code != 0:
        raise RuntimeError(
            f"B站接口 code={code} message={payload.get('message', '')}"
        )

    items = payload.get("data", {}).get("items", [])
    author = uid
    videos: list[dict] = []

    for item in items:
        if item.get("type") != "DYNAMIC_TYPE_AV":
            continue
        modules = item.get("modules", {})
        if author == uid:
            author = modules.get("module_author", {}).get("name", uid)
        archive = (
            modules.get("module_dynamic", {}).get("major", {}).get("archive", {})
        )
        bvid = archive.get("bvid", "")
        title = archive.get("title", "?")
        if bvid:
            videos.append({"bvid": bvid, "title": title})
        if len(videos) >= 5:
            break

    return author, videos


async def _check_uid(client: httpx.AsyncClient, uid: str) -> str | None:
    try:
        author, videos = await _fetch_videos(client, uid)
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
    lines = [
        f"《{v['title']}》\nhttps://www.bilibili.com/video/{v['bvid']}"
        for v in new_videos
    ]
    return header + "\n\n" + "\n\n".join(lines)


@scheduler.scheduled_job("interval", seconds=_POLL_INTERVAL, id="bilibili_video_poll")
async def _poll_bilibili() -> None:
    if not _NOTIFY_GROUPS or not _UIDS:
        return

    bots = get_bots()
    if not bots:
        _mark_offline("无在线 bot")
        return

    bot = next(iter(bots.values()))
    try:
        status = await bot.get_status()
    except Exception as e:  # noqa: BLE001
        _mark_offline(f"get_status 失败：{e}")
        return
    if not status.get("online", False):
        _mark_offline("QQ 账号已离线")
        return

    _mark_online()

    messages: list[str] = []
    proxy = _BILI_PROXY or None
    async with httpx.AsyncClient(proxy=proxy) as client:
        for uid in _UIDS:
            msg = await _check_uid(client, uid)
            if msg:
                messages.append(msg)

    if not messages:
        return

    try:
        for group_id in _NOTIFY_GROUPS:
            for msg in messages:
                await bot.send_group_msg(group_id=int(group_id), message=msg)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[bilibili_notify] 推送失败：{e}")
