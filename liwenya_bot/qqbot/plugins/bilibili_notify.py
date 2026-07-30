"""bilibili_notify · B站UP主最新视频提醒插件

每隔 BILI_POLL_INTERVAL 秒轮询一次 UP 主空间的视频列表，
发现新视频就推送到指定群。不需要登录也能查公开的 wbi 签名 key，
但 B 站对 x/space/wbi/arc/search 接口风控较严，强烈建议填一个
真实登录态的 Cookie（BILI_COOKIE），否则大概率被 412 拦截。

配置（在 .env 里追加）：
    BILI_NOTIFY_GROUPS=["群号1","群号2"]   必填，接收通知的群 QQ 号列表
    BILI_UID=178757758                       必填，要监控的 UP 主 UID
    BILI_POLL_INTERVAL=300                    可选，轮询间隔秒，默认 300（5 分钟）
    BILI_COOKIE=buvid3=xxx; SESSDATA=xxx;...  强烈建议填，否则容易被风控拦截
"""
import hashlib
import json
import os
import time
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv
import httpx
from nonebot import get_bot, logger, require

# 同 fandom_notify：显式加载 .env 确保自定义变量进入 os.environ
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

# ---- 配置 ----
_NOTIFY_GROUPS: list[str] = json.loads(
    os.environ.get("BILI_NOTIFY_GROUPS", "[]")
)
_UID: str = os.environ.get("BILI_UID", "")
_POLL_INTERVAL: int = int(os.environ.get("BILI_POLL_INTERVAL", "300"))
_COOKIE: str = os.environ.get("BILI_COOKIE", "")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# WBI 签名用的混淆表，B 站前端固定值，不会频繁变
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]

# wbi img_key/sub_key 缓存（B 站每天变一次，缓存 1 小时足够安全）
_wbi_keys_cache: dict = {"mixin_key": "", "fetched_at": 0.0}
_WBI_CACHE_TTL = 3600

# 记录已推送过的最新视频 bvid，启动时用当前最新视频初始化，避免把历史投稿全量推送
_last_bvid: str = ""

# 离线状态标记，避免每轮都刷同一句日志；仅在状态变化时输出一次
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


def _headers() -> dict:
    headers = {
        "User-Agent": _UA,
        "Referer": f"https://space.bilibili.com/{_UID}",
    }
    if _COOKIE:
        headers["Cookie"] = _COOKIE
    return headers


def _get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in _MIXIN_KEY_ENC_TAB)[:32]


async def _get_wbi_mixin_key(client: httpx.AsyncClient) -> str:
    """拿 wbi 签名用的 mixin_key，缓存 1 小时。"""
    now = time.time()
    if _wbi_keys_cache["mixin_key"] and now - _wbi_keys_cache["fetched_at"] < _WBI_CACHE_TTL:
        return _wbi_keys_cache["mixin_key"]

    resp = await client.get(
        "https://api.bilibili.com/x/web-interface/nav", headers=_headers()
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


async def _fetch_latest_videos(client: httpx.AsyncClient) -> list[dict]:
    """按发布时间倒序拿最近的几个视频，返回 [{bvid,title,pubdate}, ...]。"""
    mixin_key = await _get_wbi_mixin_key(client)
    params = _sign_params(
        {"mid": _UID, "pn": "1", "ps": "5", "order": "pubdate"}, mixin_key
    )
    resp = await client.get(
        "https://api.bilibili.com/x/space/wbi/arc/search",
        params=params,
        headers=_headers(),
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
            "pubdate": v.get("created", 0),
        }
        for v in vlist
    ]


def _format_video(v: dict) -> str:
    return f"《{v['title']}》\nhttps://www.bilibili.com/video/{v['bvid']}"


@scheduler.scheduled_job("interval", seconds=_POLL_INTERVAL, id="bilibili_video_poll")
async def _poll_bilibili() -> None:
    global _last_bvid

    if not _NOTIFY_GROUPS or not _UID:
        return  # 未配置推送群或 UID，静默跳过

    # 离线感知：跟 fandom_notify 一致，WS 会话存在不代表 QQ 账号真的在线
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

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            videos = await _fetch_latest_videos(client)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[bilibili_notify] 拉取视频列表失败：{e}"
            + ("" if _COOKIE else "（未配置 BILI_COOKIE，B 站接口对匿名请求风控很严，建议填一个登录态 Cookie）")
        )
        return

    if not videos:
        return

    latest = videos[0]

    if not _last_bvid:
        # 首次启动，只记录基线，不推送历史投稿
        _last_bvid = latest["bvid"]
        return

    if latest["bvid"] == _last_bvid:
        return  # 没有新视频

    # 按发布时间从旧到新排列，找出所有比记录里更新的视频（一般只有 1 条）
    new_videos = []
    for v in videos:
        if v["bvid"] == _last_bvid:
            break
        new_videos.append(v)
    new_videos.reverse()

    if not new_videos:
        _last_bvid = latest["bvid"]
        return

    header = "📺 UP 主发新视频了："
    lines = [_format_video(v) for v in new_videos]
    msg = header + "\n\n" + "\n\n".join(lines)

    try:
        bot = get_bot()
        for group_id in _NOTIFY_GROUPS:
            await bot.send_group_msg(group_id=int(group_id), message=msg)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[bilibili_notify] 推送消息失败：{e}")
        return  # 推送失败，不滑动记录，下轮重试

    # 推送成功，滑动到最新
    _last_bvid = latest["bvid"]
