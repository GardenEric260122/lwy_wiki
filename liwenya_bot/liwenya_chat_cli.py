"""李文亚人格 · 命令行对话测试

用中转 API（OpenAI 兼容）验证李文亚风格对话效果，多轮上下文。
先在命令行调好人格，再考虑接入 QQ。

## 配置（用环境变量，勿把密钥写进代码）

    export LIWENYA_BASE_URL="https://ai.aiclick.cc/v1"
    export LIWENYA_API_KEY="sk-你的新密钥"
    export LIWENYA_MODEL="grok-cx"        # 换成 grok-cx 分组实际的模型名

## 安装依赖

    .venv/bin/pip install openai

## 运行

    .venv/bin/python liwenya_bot/liwenya_chat_cli.py

输入消息回车对话；输入 exit / quit / 退出 结束；输入 reset 清空上下文。
"""
import os
import sys

try:
    from openai import OpenAI
except ImportError:
    print("缺少依赖，请先运行： .venv/bin/pip install openai")
    sys.exit(1)

# 自动读取 liwenya_bot/.env（密钥写在那里，不出现在命令行/对话中）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

BASE_URL = os.environ.get('LIWENYA_BASE_URL', 'https://ai.aiclick.cc/v1')
API_KEY = os.environ.get('LIWENYA_API_KEY', '')
MODEL = os.environ.get('LIWENYA_MODEL', 'grok-cx')

PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'liwenya_persona.txt')
# 保留最近多少轮对话（控制上下文长度与成本）
MAX_TURNS = 12


def load_persona():
    with open(PERSONA_FILE, encoding='utf-8') as f:
        return f.read()


def main():
    if not API_KEY:
        print("❌ 未设置 LIWENYA_API_KEY 环境变量。请先 export（见脚本顶部说明）。")
        sys.exit(1)

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    system_prompt = load_persona()
    history = []  # 只存 user/assistant 轮次

    print("=" * 50)
    print(f"  李文亚人格测试  |  模型: {MODEL}")
    print(f"  接入: {BASE_URL}")
    print("  输入消息对话；exit/quit/退出 结束；reset 清空上下文")
    print("=" * 50)

    while True:
        try:
            user_input = input("\n你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not user_input:
            continue
        if user_input.lower() in ('exit', 'quit', '退出'):
            print("再见。")
            break
        if user_input.lower() == 'reset':
            history = []
            print("（上下文已清空）")
            continue

        history.append({'role': 'user', 'content': user_input})
        # 截断到最近 MAX_TURNS 轮
        trimmed = history[-MAX_TURNS * 2:]
        messages = [{'role': 'system', 'content': system_prompt}] + trimmed

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.9,        # 高温度保持"暴躁不羁"
                max_tokens=800,
            )
            reply = resp.choices[0].message.content
        except Exception as e:  # noqa: BLE001
            print(f"\n⚠️ 调用失败：{e}")
            print("  检查：模型名是否正确 / 密钥是否有效 / base_url 是否正确 / 余额是否充足")
            history.pop()  # 回滚这轮，避免污染上下文
            continue

        print(f"\n李文亚 > {reply}")
        history.append({'role': 'assistant', 'content': reply})


if __name__ == "__main__":
    main()
