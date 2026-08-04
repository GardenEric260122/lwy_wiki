"""bilibili_notify · B站UP主最新视频提醒插件

配置（在 .env 里追加）：
    BILI_NOTIFY_GROUPS=["群号1","群号2"]    必填，接收通知的群
    BILI_UIDS=["UID1","UID2"]               必填，要监控的 UP 主
    BILI_UID=xxxxxxx                         兼容旧配置（BILI_UIDS 优先）
    BILI_TICK_SECONDS=300                    可选，每次只查 1 个 UID，两次查询的间隔秒数
    BILI_COOKIE=SESSDATA=...;bili_jct=...    可选，强烈建议填登录态（见下）

关于请求频率（2026-08 实测，别改回去）：
B站对单 IP 的 space/wbi/arc/search 配额很紧。实测同 IP 连续请求时，
第一次成功之后接下来 4 分钟内 8 次全部 412/-352，且 30 秒间隔也救不回来。
所以这里刻意做成「每 tick 只查 1 个 UID，轮着来」：
    4 个 UID + BILI_TICK_SECONDS=300 → 每小时 12 次请求，每个 UID 每 20 分钟被查一次
旧实现是每 300 秒把 4 个 UID 全查一遍（每小时 48 次），这正是 IP 被标记的原因。
发视频这种事晚 20 分钟推没影响，被风控封掉才是真的收不到。

关于 BILI_COOKIE：
只需要登录态字段（SESSDATA、bili_jct），指纹字段（buvid3/buvid4/b_nut）不用填，
代码每次会自己申请全新的——填旧 buvid 反而会直接触发 -352。
带登录态的请求配额明显高于匿名，如果你经常收不到推送，补 SESSDATA 是最有效的一步。
"""
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
import httpx
from nonebot import get_bots, logger, require

load_dotenv(Path(__file__).parent.parent / ".env", override=False)

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

try:  # nonebot 以包形式加载 plugins/，相对导入可用
    from ._bili_api import BiliBanned, BiliSession
except ImportError:  # 直接跑脚本时的兜底
    from _bili_api import BiliBanned, BiliSession  # type: ignore[no-redef]


def _parse_groups() -> list[str]:
    raw = os.environ.get("BILI_NOTIFY_GROUPS", "[]")
    try:
        return [str(g).strip() for g in json.loads(raw) if str(g).strip()]
    except (ValueError, TypeError):
        logger.error(f"[bilibili_notify] BILI_NOTIFY_GROUPS 不是合法 JSON 数组：{raw!r}")
        return []


def _parse_uids() -> list[str]:
    raw = os.environ.get("BILI_UIDS", "").strip()
    if raw:
        try:
            return [str(u).strip() for u in json.loads(raw) if str(u).strip()]
        except (ValueError, TypeError):
            logger.error(f"[bilibili_notify] BILI_UIDS 不是合法 JSON 数组：{raw!r}")
            return []
    single = os.environ.get("BILI_UID", "").strip()
    return [single] if single else []


_NOTIFY_GROUPS: list[str] = _parse_groups()
_UIDS: list[str] = _parse_uids()
# 兼容旧变量名 BILI_POLL_INTERVAL，语义已变（现在是「每次查 1 个 UID 的间隔」）
_TICK_SECONDS: int = int(
    os.environ.get("BILI_TICK_SECONDS")
    or os.environ.get("BILI_POLL_INTERVAL")
    or "300"
)

# 被风控后的退避：翻倍增长，封顶 2 小时。别做成每 tick 都重试，
# 那样会不停向 SPI 申请新指纹，本身就是被标记的原因。
_BACKOFF_BASE = 600
_BACKOFF_CAP = 7200

_STATE_FILE = Path(__file__).parent.parent / "bili_state.json"

_session = BiliSession(os.environ.get("BILI_COOKIE", ""))
_last_bvids: dict[str, str] = {}
_cursor: int = 0
_was_offline: bool = False
_ban_streak: int = 0
_banned_until: float = 0.0


def _load_state() -> None:
    """从磁盘恢复已推送位置。不做这件事的话，每次重启都会把最新视频重推一遍。"""
    global _last_bvids, _cursor
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[bilibili_notify] 状态文件读取失败，按首次运行处理：{exc}")
        return
    if isinstance(data.get("last_bvids"), dict):
        _last_bvids = {str(k): str(v) for k, v in data["last_bvids"].items()}
    if isinstance(data.get("cursor"), int):
        _cursor = data["cursor"]
    logger.info(f"[bilibili_notify] 已恢复 {len(_last_bvids)} 个 UID 的推送位置")


def _save_state() -> None:
    try:
        _STATE_FILE.write_text(
            json.dumps(
                {"last_bvids": _last_bvids, "cursor": _cursor},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[bilibili_notify] 状态写入失败：{exc}")


_load_state()


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


def _note_ban(reason: str) -> None:
    global _ban_streak, _banned_until
    _ban_streak += 1
    wait = min(_BACKOFF_BASE * (2 ** (_ban_streak - 1)), _BACKOFF_CAP)
    _banned_until = time.time() + wait
    logger.warning(
        f"[bilibili_notify] 被风控（第 {_ban_streak} 次）：{reason}；"
        f"退避 {wait // 60} 分钟后再试"
    )


def _note_ok() -> None:
    global _ban_streak
    if _ban_streak:
        logger.info(f"[bilibili_notify] 风控已恢复（此前连续 {_ban_streak} 次）")
        _ban_streak = 0


def _diff_new_videos(uid: str, videos: list[dict]) -> list[dict]:
    """返回比已记录位置更新的视频；首次见到该 UID 时只记录位置，不推历史。"""
    latest = videos[0]["bvid"]
    known = _last_bvids.get(uid)

    if not known:
        _last_bvids[uid] = latest
        _save_state()
        logger.info(f"[bilibili_notify] UID {uid} 首次记录位置 {latest}，不推历史")
        return []

    if latest == known:
        return []

    fresh: list[dict] = []
    for video in videos:
        if video["bvid"] == known:
            break
        fresh.append(video)
    fresh.reverse()  # 按时间正序推
    return fresh


async def _online_bot():
    """拿到一个「QQ 账号确实在线」的 bot；WS 连着不代表账号没被踢下线。"""
    bots = get_bots()
    if not bots:
        _mark_offline("无在线 bot（WS 会话都不存在）")
        return None
    bot = next(iter(bots.values()))
    try:
        status = await bot.get_status()
    except Exception as exc:  # noqa: BLE001
        _mark_offline(f"get_status 调用失败：{exc}")
        return None
    if not status.get("online", False):
        _mark_offline("QQ 账号已离线（get_status.online=False）")
        return None
    _mark_online()
    return bot


@scheduler.scheduled_job("interval", seconds=_TICK_SECONDS, id="bilibili_video_poll")
async def _poll_bilibili() -> None:
    global _cursor

    if not _NOTIFY_GROUPS or not _UIDS:
        return

    if time.time() < _banned_until:
        return  # 退避中，连请求都不发

    bot = await _online_bot()
    if bot is None:
        return

    # 每 tick 只查一个 UID，轮着来。这是刻意的，理由见模块开头。
    uid = _UIDS[_cursor % len(_UIDS)]
    _cursor = (_cursor + 1) % len(_UIDS)
    _save_state()

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            author, videos = await _session.fetch_videos(client, uid)
    except BiliBanned as exc:
        _note_ban(f"UID {uid} {exc}")
        return
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[bilibili_notify] UID {uid} 拉取失败：{exc}")
        return

    _note_ok()

    if not videos:
        return

    fresh = _diff_new_videos(uid, videos)
    if not fresh:
        return

    fresh = fresh[-3:]  # 防刷屏
    body = "\n\n".join(
        f"《{v['title']}》\nhttps://www.bilibili.com/video/{v['bvid']}" for v in fresh
    )
    message = f"📺 {author} 发新视频了：\n\n{body}"

    sent = False
    for group_id in _NOTIFY_GROUPS:
        try:
            await bot.send_group_msg(group_id=int(group_id), message=message)
            sent = True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[bilibili_notify] 推送到群 {group_id} 失败：{exc}")

    # 只有至少推成功一个群才滑动位置，否则下轮重试，避免丢推送
    if sent:
        _last_bvids[uid] = fresh[-1]["bvid"]
        _save_state()


logger.info(
    f"[bilibili_notify] 已加载：{len(_UIDS)} 个 UID，{len(_NOTIFY_GROUPS)} 个群，"
    f"每 {_TICK_SECONDS}s 查 1 个 UID"
    + (f"（每个 UID 约 {_TICK_SECONDS * len(_UIDS) // 60} 分钟一轮）" if _UIDS else "")
    + f"，登录态：{'有' if _session.has_login else '无'}"
)
