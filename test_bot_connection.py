import pywikibot

def test_bot_connection():
    print("正在连接 Fandom 站点...")
    site = pywikibot.Site('zh', 'fandom')

    # 登录（读取 user-config.py / user-password.py 中的 BotPasswords 凭据）
    site.login()

    # 1. 检查站点信息
    print(f"✅ 成功连接至站点: {site.sitename}")
    print(f"🌐 站点语言: {site.lang}")

    # 2. 检查登录状态与账号权限
    print(f"🔑 登录状态: {'已登录' if site.logged_in() else '未登录'}")

    username = site.username()
    user = pywikibot.User(site, username)
    print(f"👤 当前登录账号: {user.username}")

    groups = user.groups()
    print(f"🛡️ 账号拥有组别: {list(groups)}")

    if 'bot' in groups:
        print("🎉 恭喜：当前账号已拥有 Bot Flag（机器人标识）！")
    else:
        print("⚠️ 提示：当前账号尚无 Bot 标识，编辑会显示在常规最近更改中。")

if __name__ == "__main__":
    test_bot_connection()
