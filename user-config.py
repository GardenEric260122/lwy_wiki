import os

# 代理配置 —— 通过 Clash Verge 系统代理访问 Fandom
# 仅在非 CI 环境（本地）启用；GitHub Actions（CI=true）直连，无需代理
if not os.environ.get('CI'):
    _PROXY = 'http://127.0.0.1:7897'
    os.environ.setdefault('http_proxy', _PROXY)
    os.environ.setdefault('https_proxy', _PROXY)
    os.environ.setdefault('all_proxy', 'socks5://127.0.0.1:7897')

# 必须配置：指定家族与语言
family = 'fandom'
mylang = 'zh'

# 注册自定义 family 文件（fandom_family.py，与本文件同目录）
# 手写 family 文件可避免 Fandom 拦截自动探测（403）
# 使用 base_dir（pywikibot 指向配置目录）以兼容本地与 CI 不同的仓库路径
user_families_paths = [base_dir]

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
