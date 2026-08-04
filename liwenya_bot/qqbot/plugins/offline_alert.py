"""offline_alert · QQ 掉线感知与告警插件

NapCat 走非官方协议，被腾讯踢下线无法根除，只能做到「第一时间知道」。
这个插件覆盖三种信号，从快到慢：

1. bot_offline 通知事件（最快，秒级）：
   NapCat 在账号登录失效时会主动推 notice_type=bot_offline，例如
       {'notice_type': 'bot_offline', 'message': '你的账号当前登录已失效，请重新登录。'}
   直接挂事件，不用等轮询。
2. WS 断开（快）：NapCat 与本进程连接断了（NapCat 挂了/重启/容器退出）。
3. get_status 轮询（兜底）：WS 还连着、也没收到 bot_offline，但账号已经离线。

告警渠道：
    - 日志：始终输出。
    - Webhook：设置 ALERT_WEBHOOK_URL 后把纯文本 POST 过去（ntfy / Bark / 自建均可）。
      掉线时 QQ 发不出消息，这是唯一能主动触达你的通道，建议配上。
    - QQ 私聊：仅在「恢复上线」时给 SUPERUSERS 发一条确认。

配置（在 .env 里追加，都是可选的）：
    ALERT_WEBHOOK_URL=https://ntfy.sh/你的私密主题   不填则只写日志
    ALERT_CHECK_INTERVAL=60                          兜底轮询间隔秒，默认 60
    ALERT_REPEAT_MINUTES=30                          仍在掉线时每隔多少分钟重复提醒，默认 30；0=不重复
    ALERT_SELFTEST=1                                 启动时推一条自检消息，默认开

【2026-08-04 修复记录】
8 月 4 日 01:46 账号掉线、直到 15:10 才恢复，13.5 小时零推送。原因不是 ntfy 不可用，
而是本模块在 import 时把 ALERT_WEBHOOK_URL 读成模块级常量：进程 23:32 启动时该变量还没写进
.env（00:14 才补上），此后进程内它永远是空串，_send_webhook() 第一行就 return 了。
三处改动：
  1. Webhook 地址改为「每次告警时从 .env 现读」，改配置不必重启也能生效。
  2. 推送失败重试 3 次（指数退避），并记录 HTTP 状态码——静默失败不再无迹可寻。
  3. 掉线未恢复时按 ALERT_REPEAT_MINUTES 重复提醒，避免单条通知被错过后再无下文；
     另加启动自检推送，让「通道通不通」在启动时就有结论。
"""
import asyncio
import os
from datetime import datetime
from email.header import Header
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
import httpx
from nonebot import get_bots, get_driver, logger, on_notice, require

_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(_ENV_PATH, override=False)

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler  # noqa: E402

_CHECK_INTERVAL: int = int(os.environ.get("ALERT_CHECK_INTERVAL", "60"))
_REPEAT_MINUTES: int = int(os.environ.get("ALERT_REPEAT_MINUTES", "30"))
_SELFTEST: bool = os.environ.get("ALERT_SELFTEST", "1").strip() not in ("0", "false", "False", "")

# None 表示还没测过，避免进程刚起来就误报一次「已恢复」
_last_online: bool | None = None
# 连续掉线的轮询次数，用于按 ALERT_REPEAT_MINUTES 重复提醒
_offline_ticks: int = 0

driver = get_driver()


def _webhook_url() -> str:
    """每次告警时现读 .env，改了地址不必重启进程。

    读文件失败（被删/权限变更）时退回进程环境变量，保证不会因为读配置而丢告警。
    """
    try:
        value = (dotenv_values(_ENV_PATH).get("ALERT_WEBHOOK_URL") or "").strip()
        if value:
            return value
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[offline_alert] 读取 .env 失败，回退到进程环境变量：{exc}")
    return os.environ.get("ALERT_WEBHOOK_URL", "").strip()


async def _send_webhook(text: str, *, title: str = "李文亚Bot告警", priority: str = "high") -> bool:
    """把告警文本 POST 到用户自己配置的地址。失败重试 3 次，返回是否成功。"""
    url = _webhook_url()
    if not url:
        logger.error(
            "[offline_alert] ALERT_WEBHOOK_URL 未配置，本条告警只能进日志。"
            "请在 .env 填入 ntfy 等推送地址（改完即时生效，无需重启）"
        )
        return False

    # ntfy 识别这几个头做标题与高优先级提醒；其他服务会忽略，无副作用。
    # HTTP 头只能是 ASCII/latin-1，中文标题必须按 RFC 2047 编码（ntfy 已验证支持），
    # 否则 httpx 会抛 UnicodeEncodeError，告警一条都发不出去。
    headers = {
        "Title": Header(title, "utf-8").encode(),
        "Priority": priority,
        "Tags": "warning",
    }
    last_error = ""
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, content=text.encode("utf-8"), headers=headers)
            if resp.status_code < 400:
                logger.info(f"[offline_alert] Webhook 推送成功（HTTP {resp.status_code}）")
                return True
            last_error = f"HTTP {resp.status_code} {resp.text[:120]}"
        except Exception as exc:  # noqa: BLE001
            last_error = repr(exc)
        if attempt < 3:
            await asyncio.sleep(2 ** attempt)  # 2s, 4s
        logger.warning(f"[offline_alert] Webhook 第 {attempt} 次推送失败：{last_error}")

    logger.error(f"[offline_alert] Webhook 三次推送均失败，告警未送达：{last_error}")
    return False


async def _notify_superusers(text: str) -> None:
    """给 SUPERUSERS 发私聊。仅在恢复后调用——离线时这一步必然失败。"""
    bots = get_bots()
    if not bots:
        return
    bot = next(iter(bots.values()))
    for user_id in driver.config.superusers:
        try:
            await bot.send_private_msg(user_id=int(user_id), message=text)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[offline_alert] 给 {user_id} 发送私聊失败：{exc}")


async def _alert(text: str, *, also_qq: bool = False, priority: str = "high") -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full = f"[{stamp}] {text}"
    logger.warning(f"[offline_alert] {text}")
    await _send_webhook(full, priority=priority)
    if also_qq:
        await _notify_superusers(full)


_bot_offline_notice = on_notice(priority=5, block=False)


@_bot_offline_notice.handle()
async def _on_bot_offline_notice(event) -> None:
    """NapCat 主动推的账号下线通知，这是最快的信号。"""
    global _last_online, _offline_ticks
    if getattr(event, "notice_type", "") != "bot_offline":
        return
    _last_online = False
    _offline_ticks = 0
    detail = getattr(event, "message", "") or "账号登录已失效"
    await _alert(f"⚠️ NapCat 通报账号下线：{detail}，需要去 WebUI 重新扫码", priority="urgent")


@driver.on_bot_disconnect
async def _on_disconnect(bot) -> None:
    """WS 断开是强信号，立刻告警，不等下一次健康检查。"""
    global _last_online, _offline_ticks
    _last_online = False
    _offline_ticks = 0
    await _alert(f"⚠️ 机器人 {bot.self_id} 的 WebSocket 已断开，请检查 NapCat 是否存活")


@driver.on_startup
async def _startup_selftest() -> None:
    """启动时推一条自检，让「推送通道到底通不通」在启动阶段就有结论。"""
    if not _SELFTEST:
        return
    url = _webhook_url()
    if not url:
        logger.error(
            "[offline_alert] 启动自检跳过：ALERT_WEBHOOK_URL 未配置。"
            "掉线时你将收不到任何提醒，请尽快在 .env 配上"
        )
        return
    ok = await _send_webhook(
        f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ✅ 掉线告警通道自检通过，Bot 已启动并开始监控",
        title="李文亚Bot自检",
        priority="default",
    )
    logger.info(f"[offline_alert] 启动自检推送{'成功' if ok else '失败'}（目标 {url}）")


@scheduler.scheduled_job("interval", seconds=_CHECK_INTERVAL, id="qq_health_check")
async def _health_check() -> None:
    """兜底：WS 连着、也没收到 bot_offline，但账号已被踢。状态翻转时告警，持续掉线时定期重提。"""
    global _last_online, _offline_ticks

    bots = get_bots()
    if not bots:
        online, reason = False, "无在线 bot（WS 会话不存在）"
    else:
        bot = next(iter(bots.values()))
        try:
            status = await bot.get_status()
        except Exception as exc:  # noqa: BLE001
            online, reason = False, f"get_status 调用失败：{exc}"
        else:
            online = bool(status.get("online", False))
            reason = "" if online else "QQ 账号已被踢下线（get_status.online=False）"

    if _last_online is None:
        # 首次检查只记状态；若启动即离线也告警一次，否则会一直没人知道
        _last_online = online
        if not online:
            _offline_ticks = 0
            await _alert(f"⚠️ 启动时即为离线状态：{reason}，需要重新扫码登录")
        return

    if online:
        if not _last_online:
            _last_online = True
            _offline_ticks = 0
            await _alert("✅ 机器人已恢复在线，推送已自动继续", also_qq=True, priority="default")
        return

    # 仍处于离线
    if _last_online:
        _last_online = False
        _offline_ticks = 0
        await _alert(f"⚠️ 机器人掉线：{reason}，需要去 NapCat WebUI 重新扫码")
        return

    if _REPEAT_MINUTES <= 0:
        return
    _offline_ticks += 1
    ticks_per_repeat = max(1, _REPEAT_MINUTES * 60 // _CHECK_INTERVAL)
    if _offline_ticks % ticks_per_repeat == 0:
        minutes = _offline_ticks * _CHECK_INTERVAL // 60
        await _alert(
            f"⚠️ 仍在掉线中（已持续约 {minutes} 分钟）：{reason}，请去 NapCat WebUI 重新扫码",
            priority="urgent",
        )


logger.info(
    f"[offline_alert] 已加载：兜底轮询 {_CHECK_INTERVAL}s，"
    f"重复提醒 {_REPEAT_MINUTES or '关闭'} 分钟，"
    f"Webhook {'已配置（每次告警现读 .env）' if _webhook_url() else '未配置（掉线不会有人知道）'}"
)
