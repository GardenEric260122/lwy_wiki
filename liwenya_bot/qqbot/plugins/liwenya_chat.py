"""liwenya_chat · 李文亚风格对话插件

触发方式：
- 群聊：@机器人 + 内容
- 私聊：直接发消息
普通群消息不触发，省 token。

会话隔离：每个群、每个私聊各自独立多轮上下文。
控成本：只在被 @ / 私聊时调用；限上下文轮数；同会话冷却。
退出角色：消息含"退出/切回正常/不用演了"时，会话清空并回正常口吻提示。

配置全部走环境变量（见 .env.example），密钥不写进代码。
"""
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from nonebot import on_message, on_command, get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent
from nonebot.rule import to_me
from nonebot.matcher import Matcher

try:
    from openai import OpenAI
except ImportError as e:  # 明确报错，便于在 VPS 上定位缺依赖
    raise ImportError("缺少 openai 库，请 pip install -r requirements.txt") from e

# NoneBot2 的 pydantic-settings 不回写 os.environ，需要手动加载 .env
# 从 plugins/ 往上两级找到 qqbot/.env
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# ---- 读取配置（与命令行脚本共用同名变量）----
BASE_URL = os.environ.get("LIWENYA_BASE_URL", "https://ai.aiclick.cc/v1")
API_KEY = os.environ.get("LIWENYA_API_KEY", "")
MODEL = os.environ.get("LIWENYA_MODEL", "grok-cx")
MAX_TURNS = int(os.environ.get("LIWENYA_MAX_TURNS", "12"))
COOLDOWN = float(os.environ.get("LIWENYA_COOLDOWN", "3"))
TEMPERATURE = float(os.environ.get("LIWENYA_TEMPERATURE", "0.9"))
MAX_TOKENS = int(os.environ.get("LIWENYA_MAX_TOKENS", "800"))

# persona 文件在上一层 liwenya_bot/ 里，复用命令行那份，避免两处维护
_PERSONA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "liwenya_persona.txt",
)

_EXIT_WORDS = ("退出", "切回正常", "不用演了", "退出角色")


def _load_persona() -> str:
    with open(_PERSONA_FILE, encoding="utf-8") as f:
        return f.read()


SYSTEM_PROMPT = _load_persona()

# 惰性初始化 client，避免 import 期就因缺 key 报错
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not API_KEY:
            raise RuntimeError("未设置 LIWENYA_API_KEY，请在 .env 填入密钥")
        _client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    return _client


# ---- 会话状态：按 session_id 存历史与冷却时间 ----
# 每个值是 deque，最多存 MAX_TURNS*2 条（user/assistant 交替）
_histories: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_TURNS * 2))
_last_call: dict[str, float] = defaultdict(float)


def _session_id(event: MessageEvent) -> str:
    """群聊按群号隔离，私聊按用户号隔离。"""
    if isinstance(event, GroupMessageEvent):
        return f"group_{event.group_id}"
    return f"user_{event.user_id}"


def _call_llm(session: str, user_text: str) -> str:
    """带多轮上下文调用中转 API，返回回复文本。异常向上抛。"""
    history = _histories[session]
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    resp = _get_client().chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        timeout=60,
    )
    reply = resp.choices[0].message.content or "……（我不想说话了）"

    # 只有成功了才把这轮写进历史，避免失败污染上下文
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply})
    return reply


# ---- 命令：重置本会话上下文 ----
reset_cmd = on_command("重置", aliases={"reset", "清空"}, rule=to_me(), priority=5, block=True)


@reset_cmd.handle()
async def _handle_reset(event: MessageEvent):
    _histories.pop(_session_id(event), None)
    await reset_cmd.finish("（上下文已清空，重新开始。）")


# ---- 主对话：群里 @ 机器人 或 私聊都会触发 ----
chat = on_message(rule=to_me(), priority=10, block=True)


@chat.handle()
async def _handle_chat(bot: Bot, event: MessageEvent, matcher: Matcher):
    user_text = event.get_plaintext().strip()
    if not user_text:
        return

    session = _session_id(event)

    # 退出角色：清空上下文，跳出戏仿
    if any(w in user_text for w in _EXIT_WORDS):
        _histories.pop(session, None)
        await matcher.finish("好的，已退出角色扮演，恢复正常口吻。有需要随时再叫我。")

    # 冷却：同一会话短时间内重复触发直接忽略，防刷控成本
    now = time.time()
    if now - _last_call[session] < COOLDOWN:
        return
    _last_call[session] = now

    try:
        reply = _call_llm(session, user_text)
    except Exception as e:  # noqa: BLE001
        logger.opt(exception=e).error("调用对话 API 失败")
        await matcher.finish("（脑子一时转不过来……过会儿再问我。）")

    await matcher.finish(reply)
