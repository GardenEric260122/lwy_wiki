"""李文亚人格 · 一次性连通测试（非交互）

直接问一个固定问题并打印回复，用于验证 API 连通性与人格效果。
不需要交互输入，适合快速验证。

用法（把 KEY 换成你的真实密钥，一行跑完）：

  LIWENYA_API_KEY="sk-xxx" LIWENYA_MODEL="grok-cx" \
    .venv/bin/python liwenya_bot/test_once.py

可选：LIWENYA_BASE_URL 默认 https://ai.aiclick.cc/v1
可选：第一个命令行参数自定义提问，如：
  ... test_once.py "太阳到底有多大？"
"""
import os
import sys

from openai import OpenAI

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
QUESTION = sys.argv[1] if len(sys.argv) > 1 else '光合作用真的需要二氧化碳吗？'


def main():
    if not API_KEY:
        print("❌ 未设置 LIWENYA_API_KEY")
        sys.exit(1)

    print(f"接入: {BASE_URL}  |  模型: {MODEL}")
    print(f"提问: {QUESTION}\n" + "-" * 40)

    with open(PERSONA_FILE, encoding='utf-8') as f:
        system_prompt = f.read()

    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': QUESTION},
            ],
            temperature=0.9,
            max_tokens=800,
        )
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 调用失败：{e}")
        print("排查：模型名是否正确 / 密钥是否有效 / base_url 带 /v1 / 余额是否充足")
        sys.exit(1)

    print("李文亚 >", resp.choices[0].message.content)
    # 打印用量便于估算成本
    if resp.usage:
        print("-" * 40)
        print(f"tokens: 输入 {resp.usage.prompt_tokens} / 输出 {resp.usage.completion_tokens}")


if __name__ == "__main__":
    main()
