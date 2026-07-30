"""bilibili_notify · B站UP主最新视频提醒插件

每隔 BILI_POLL_INTERVAL 秒轮询一次所有配置的 UP 主空间视频列表，
发现新视频就推送到指定群。强烈建议填一个真实登录态的 Cookie（BILI_COOKIE），
否则大概率被 B 站 412 风控拦截。

配置（在 .env 里追加）：
    BILI_NOTIFY_GROUPS=["群号1","群号2"]        必填，接收通知的群 QQ 号列表
    BILI_UIDS=["178757758","123456789"]         必填，要监控的 UP 主 UID 列表
    BILI_UID=178757758                           兼容旧配置，单个 UID（BILI_UIDS 优先）
    BILI_POLL_INTERVAL=300                       可选，每轮轮询间隔秒，默认 300（5 分钟）
    BILI_COOKIE=buvid3=xxx; SESSDATA=xxx;...     强烈建议填，否则容易被风控拦截
"""
import asyncio
import hashlib
import json
import os
import time
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv
import httpx
from nonebot import get_bot, logger, require

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

# ---- 配置 ----
_NOTIFY_GROUPS: list[str] = json.loads(
    os.environ.get("BILI_NOTIFY_GROUPS", "[]")
)

# BILI_UIDS 优先；兼容旧的单 UID 配置 BILI_UID
_raw_uids = os.environ.get("BILI_UIDS", "")
if _raw_uids:
    _UIDS: list[str] = [u.strip() for u in json.loads(_raw_uids) if str(u).strip()]
else:
    _single = os.environ.get("BILI_UID", "").strip()
    _UIDS = [_single] if _single else []

_POLL_INTERVAL: int = int(os.environ.get("BILI_POLL_INTERVAL", "300"))
_COOKIE: str = os.environ.get("BILI_COOKIE", "")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]

_wbi_keys_cache: dict = {"mixin_key": "", "fetched_at": 0.0}
_WBI_CACHE_TTL = 3600

# 每个 UID 独立记录上次推送的最新 bvid
_last_bvids: dict[str, str] = {}

_was_offline: bool = False


def _mark_offline(reason: str) -> None:
    global _was_offline
    if not _was_offline:
        logger.warning(f"[bilibili_notify] 检测到离线，暂停推送直至恢复：{reason}")
        _was_offline = True
    else:
        logger.debug(f"[bilibili_notify] 仍处于离线，跳过本轮：{reason}")


def _mark_online() -> None:
    global _was_offline
    if _was_offline:
        logger.info("[bilibili_notify] 已恢复在线，继续推送")
        _was_offline = False


def _headers(uid: str) -> dict:
    headers = {
        "User-Agent": _UA,
        "Referer": f"https://space.bilibili.com/{uid}",
    }
    if _COOKIE:
        headers["Cookie"] = _COOKIE
    return headers


def _get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in _MIXIN_KEY_ENC_TAB)[:32]


async def _get_wbi_mixin_key(client: httpx.AsyncClient) -> str:
    now = time.time()
    if _wbi_keys_cache["mixin_key"] and now - _wbi_keys_cache["fetched_at"] < _WBI_CACHE_TTL:
        return _wbi_keys_cache["mixin_key"]

    resp = await client.get(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={"User-Agent": _UA, **({"Cookie": _COOKIE} if _COOKIE else {})},
    )
    resp.raise_for_status()
    data = resp.json()
    img_url = data["data"]["wbi_img"]["img_url"]
    sub_url = data["data"]["wbi_img"]["sub_url"]
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    mixin_key = _get_mixin_key(img_key + sub_key)

    _wbi_keys_cache["mixin_key"] = mixin_key
    _wbi_keys_cache["fetched_at"] = now
    return mixin_key


def _sign_params(params: dict, mixin_key: str) -> dict:
    signed = dict(params)
    signed["wts"] = str(int(time.time()))
    signed = dict(sorted(signed.items()))
    query = urllib.parse.urlencode(signed)
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return signed


async def _fetch_latest_videos(client: httpx.AsyncClient, uid: str, mixin_key: str) -> list[dict]:
    """返回 [{bvid, title, author, pubdate}, ...]，按发布时间倒序。"""
    params = _sign_params({"mid": uid, "pn": "1", "ps": "5", "order": "pubdate"}, mixin_key)
    resp = await client.get(
        "https://api.bilibili.com/x/space/wbi/arc/search",
        params=params,
        headers=_headers(uid),
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"code={data.get('code')} msg={data.get('message')}")
    vlist = data.get("data", {}).get("list", {}).get("vlist", [])
    return [
        {
            "bvid": v.get("bvid", ""),
            "title": v.get("title", "?"),
            "author": v.get("author", uid),  # vlist 里直接带 UP 主名字
            "pubdate": v.get("created", 0),
        }
        for v in vlist
    ]


def _format_video(v: dict) -> str:
    return f"《{v['title']}》\nhttps://www.bilibili.com/video/{v['bvid']}"


async def _check_uid(client: httpx.AsyncClient, uid: str, mixin_key: str) -> str | None:
    """检查单个 UID 是否有新视频，有则返回推送消息文本，无则返回 None。"""
    global _last_bvids

    try:
        videos = await _fetch_latest_videos(client, uid, mixin_key)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[bilibili_notify] UID {uid} 拉取失败：{e}"
            + ("" if _COOKIE else "（建议配置 BILI_COOKIE）")
        )
        return None

    if not videos:
        return None

    latest = videos[0]
    last = _last_bvids.get(uid)

    if not last:
        # 首次：仅记录基线，不推历史投稿
        _last_bvids[uid] = latest["bvid"]
        return None

    if latest["bvid"] == last:
        return None  # 没有新视频

    new_videos = []
    for v in videos:
        if v["bvid"] == last:
            break
        new_videos.append(v)
    new_videos.reverse()

    if not new_videos:
        _last_bvids[uid] = latest["bvid"]
        return None

    author = new_videos[0]["author"]
    header = f"📺 {author} 发新视频了："
    lines = [_format_video(v) for v in new_videos]
    return header + "\n\n" + "\n\n".join(lines)


@scheduler.scheduled_job("interval", seconds=_POLL_INTERVAL, id="bilibili_video_poll")
async def _poll_bilibili() -> None:
    if not _NOTIFY_GROUPS or not _UIDS:
        return

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

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            mixin_key = await _get_wbi_mixin_key(client)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[bilibili_notify] 获取 WBI key 失败：{e}")
            return

        messages: list[str] = []
        for i, uid in enumerate(_UIDS):
            if i > 0:
                await asyncio.sleep(2)  # 多 UID 时请求间隔，避免触发限流
            msg = await _check_uid(client, uid, mixin_key)
            if msg:
                messages.append(msg)
                _last_bvids[uid] = _last_bvids[uid]  # 已在 _check_uid 内更新

    if not messages:
        return

    try:
        bot = get_bot()
        for group_id in _NOTIFY_GROUPS:
            for msg in messages:
                await bot.send_group_msg(group_id=int(group_id), message=msg)
                if len(messages) > 1:
                    await asyncio.sleep(1)  # 同群多条消息间隔，防刷屏
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[bilibili_notify] 推送消息失败：{e}")
