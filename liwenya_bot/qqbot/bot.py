"""NoneBot2 入口 · 李文亚 QQ 机器人

在 VPS 上运行：
    cd liwenya_bot/qqbot
    python bot.py

前提：
1. NapCat 已登录 QQ 小号，并配置了指向本进程的 OneBot v11 反向 WebSocket
   （见同目录 DEPLOY.md）。
2. 上一层 liwenya_bot/.env 已填好 API 配置，或本目录 .env 覆盖。
"""
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

# 初始化：读取 .env / .env.prod 等配置
nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 加载本地插件目录
nonebot.load_plugins("plugins")

if __name__ == "__main__":
    nonebot.run()
