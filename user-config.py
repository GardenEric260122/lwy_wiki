import os

# 代理配置 —— 通过 Clash Verge 系统代理访问 Fandom
# pywikibot 底层使用 requests，会读取以下环境变量；在此设置后
# 运行脚本时无需再手动 export 代理变量
_PROXY = 'http://127.0.0.1:7897'
os.environ.setdefault('http_proxy', _PROXY)
os.environ.setdefault('https_proxy', _PROXY)
os.environ.setdefault('all_proxy', 'socks5://127.0.0.1:7897')

# 必须配置：指定家族与语言
family = 'fandom'
mylang = 'zh'

# 注册自定义 family 文件（fandom_family.py，与本文件同目录）
# 手写 family 文件可避免 Fandom 拦截自动探测（403）
# user_families_paths 会在 user-config 执行后由 pywikibot 统一注册
user_families_paths = ['/Users/zhangjinming/my-project']

# 登录用户名
usernames['fandom']['zh'] = 'WenyaverseBot'

# BotPasswords 凭据文件（与本文件同目录，含明文密码，已被 .gitignore 忽略）
password_file = 'user-password.py'

# 自定义 User-Agent —— Fandom 会拦截 pywikibot 默认 UA（返回 403），
# 需伪装成浏览器 UA 才能正常访问
user_agent_format = 'Mozilla/5.0 (WenyaverseBot/1.0; +https://wenyaverse.fandom.com/zh)'

# 减缓编辑速率，避免被服务器拦截（单位：秒）
minthrottle = 2
maxthrottle = 5
