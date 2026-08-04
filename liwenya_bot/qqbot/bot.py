"""NoneBot2 入口 · 李文亚 QQ 机器人

在 VPS 上运行：
    cd liwenya_bot/qqbot
    python bot.py

前提：
1. NapCat 已登录 QQ 小号，并配置了指向本进程的 OneBot v11 反向 WebSocket
   （见同目录 DEPLOY.md）。
2. 上一层 liwenya_bot/.env 已填好 API 配置，或本目录 .env 覆盖。
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 优先加载 qqbot/.env，再补全上一层 liwenya_bot/.env（override=False 不覆盖已有值）
_bot_dir = Path(__file__).parent
load_dotenv(_bot_dir / ".env", override=False)
load_dotenv(_bot_dir.parent / ".env", override=False)

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter


def _preflight_check() -> None:
    """启动前检查关键配置，把常见的填错问题在启动阶段就暴露出来。"""
    errors: list[str] = []
    warnings: list[str] = []

    api_key = os.environ.get("LIWENYA_API_KEY", "")
    base_url = os.environ.get("LIWENYA_BASE_URL", "")
    model = os.environ.get("LIWENYA_MODEL", "")

    if not api_key:
        errors.append("LIWENYA_API_KEY 未设置，请在 .env 填入 API 密钥")
    if not base_url:
        errors.append("LIWENYA_BASE_URL 未设置")
    elif not base_url.rstrip("/").endswith("/v1"):
        warnings.append(
            f"LIWENYA_BASE_URL={base_url!r} 不以 /v1 结尾，"
            "大多数 OpenAI 兼容中转需要 /v1，请确认（典型地址：https://ai.aiclick.cc/v1）"
        )
    if not model:
        errors.append("LIWENYA_MODEL 未设置，请在 .env 填入模型名（如 claude-sonnet-5）")

    for w in warnings:
        print(f"[preflight WARNING] {w}", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"[preflight ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    # 验证模型名在中转 API 的可用列表里
    if api_key and base_url and model:
        try:
            from openai import OpenAI
            available = [m.id for m in OpenAI(base_url=base_url, api_key=api_key).models.list().data]
            if model not in available:
                # 不退出——中转有时不列出但实际可用，降级为 WARNING
                print(
                    f"[preflight WARNING] 模型 {model!r} 未出现在中转 models.list() 返回中。"
                    f"\n  可用模型（含 claude）：{[x for x in available if 'claude' in x]}",
                    file=sys.stderr,
                )
            else:
                print(f"[preflight OK] 模型 {model!r} 已确认可用", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"[preflight WARNING] 无法验证模型可用性（{exc}），继续启动", file=sys.stderr)



def _check_notify_config() -> None:
    """检查推送插件的配置。这些不是致命错误，但配错了插件会静默不工作，
    所以在启动阶段就说清楚，而不是等用户发现「怎么没推送」。"""
    import json as _json

    def _as_list(key: str) -> list | None:
        raw = os.environ.get(key, "").strip()
        if not raw:
            return None
        try:
            value = _json.loads(raw)
        except ValueError:
            print(
                f"[preflight WARNING] {key}={raw!r} 不是合法 JSON 数组，"
                f"该插件将不工作。正确写法：{key}=[\"123456\"]",
                file=sys.stderr,
            )
            return None
        if not isinstance(value, list):
            print(f"[preflight WARNING] {key} 必须是 JSON 数组", file=sys.stderr)
            return None
        return value

    bili_groups = _as_list("BILI_NOTIFY_GROUPS")
    bili_uids = _as_list("BILI_UIDS") or (
        [os.environ["BILI_UID"]] if os.environ.get("BILI_UID", "").strip() else None
    )
    if bili_groups and bili_uids:
        tick = int(
            os.environ.get("BILI_TICK_SECONDS")
            or os.environ.get("BILI_POLL_INTERVAL")
            or "300"
        )
        print(
            f"[preflight OK] B站推送：{len(bili_uids)} 个 UID → {len(bili_groups)} 个群，"
            f"每 {tick}s 查 1 个（每个 UID 约 {tick * len(bili_uids) // 60} 分钟一轮）",
            file=sys.stderr,
        )
    elif bili_groups or bili_uids:
        missing = "BILI_UIDS" if not bili_uids else "BILI_NOTIFY_GROUPS"
        print(
            f"[preflight WARNING] B站推送只配了一半，缺 {missing}，插件不会推任何消息",
            file=sys.stderr,
        )

    cookie = os.environ.get("BILI_COOKIE", "")
    if cookie:
        has_login = "SESSDATA=" in cookie
        has_fp = "buvid3=" in cookie
        if not has_login and has_fp:
            print(
                "[preflight WARNING] BILI_COOKIE 里只有 buvid 指纹、没有 SESSDATA。"
                "指纹现在由代码自动申请，旧 buvid 反而会触发 -352 风控（已自动忽略）。"
                "建议改填 SESSDATA=...;bili_jct=... 以获得更高配额",
                file=sys.stderr,
            )

    if not _as_list("FANDOM_NOTIFY_GROUPS"):
        print(
            "[preflight WARNING] FANDOM_NOTIFY_GROUPS 未配置，Wiki 变更推送不会工作",
            file=sys.stderr,
        )

    alert_url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not alert_url:
        print(
            "[preflight WARNING] ALERT_WEBHOOK_URL 未配置。QQ 掉线时机器人发不出消息，"
            "没有 Webhook 就只能靠翻日志才能发现掉线",
            file=sys.stderr,
        )
    elif not alert_url.startswith(("http://", "https://")):
        # 只填了 ntfy 主题名、漏了协议头的情况，httpx 会直接抛错，等到掉线才发现就太晚了
        print(
            f"[preflight WARNING] ALERT_WEBHOOK_URL={alert_url!r} 不像合法 URL，"
            "应以 http:// 或 https:// 开头（例：https://ntfy.sh/你的主题名）",
            file=sys.stderr,
        )
    else:
        print(f"[preflight OK] 掉线告警 Webhook 已配置：{alert_url}", file=sys.stderr)


_preflight_check()
_check_notify_config()

# 初始化：读取 .env / .env.prod 等配置
nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 加载本地插件目录
nonebot.load_plugins("plugins")

if __name__ == "__main__":
    nonebot.run()
