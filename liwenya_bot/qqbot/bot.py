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


_preflight_check()

# 初始化：读取 .env / .env.prod 等配置
nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 加载本地插件目录
nonebot.load_plugins("plugins")

if __name__ == "__main__":
    nonebot.run()
