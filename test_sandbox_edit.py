"""沙盒编辑测试脚本

在指定的沙盒页上执行一次安全的「写入 → 读回校验」流程，
用于验证 Bot 的**编辑权限**是否正常。

用法::

    # 默认：机器人自己的用户子页（最安全，不影响正式内容）
    .venv/bin/python test_sandbox_edit.py

    # 指定公共沙盒页
    .venv/bin/python test_sandbox_edit.py "Project:沙盒"

前提：
  1. Clash Verge 代理已开启（user-config.py 已内置 127.0.0.1:7897）；
  2. user-config.py / user-password.py 凭据有效（已通过 test_bot_connection.py 验证）。
"""
import sys
import pywikibot

# 默认沙盒页：机器人自己的用户子页，避免影响正式内容
DEFAULT_SANDBOX = 'User:WenyaverseBot/sandbox'


def test_sandbox_edit(title):
    print("正在连接并登录 Fandom 站点...")
    site = pywikibot.Site('zh', 'fandom')
    site.login()

    if not site.logged_in():
        print("❌ 登录失败，请先运行 test_bot_connection.py 排查凭据。")
        return

    print(f"✅ 已登录：{site.username()}")

    page = pywikibot.Page(site, title)
    print(f"📄 目标沙盒页：{page.title()}")
    print(f"   页面当前{'存在' if page.exists() else '不存在（将新建）'}")

    marker = 'pywikibot-sandbox-edit-test'
    new_text = (
        "{{测试页面}}\n"
        "这是一次由 WenyaverseBot 通过 Pywikibot 执行的自动化写入测试。\n\n"
        f"标记：<code>{marker}</code>\n"
    )

    # 1. 写入
    print("✏️  正在写入测试内容...")
    page.text = new_text
    page.save(summary='机器人编辑权限测试（自动化沙盒写入）', bot=True)
    print("   写入请求已提交。")

    # 2. 读回校验
    page_check = pywikibot.Page(site, title)
    fetched = page_check.get(force=True)
    if marker in fetched:
        print("🎉 校验成功：写入的标记已在页面中读回，Bot 编辑权限正常！")
        print(f"🔗 查看：https://wenyaverse.fandom.com/zh/wiki/{page.title(as_url=True)}")
    else:
        print("⚠️ 校验失败：未在读回内容中找到标记，请手动检查页面。")


if __name__ == "__main__":
    sandbox_title = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SANDBOX
    test_sandbox_edit(sandbox_title)
