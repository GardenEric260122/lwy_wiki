# 李文亚 QQ 机器人 · 境外 VPS 部署清单

> 环境：境外 VPS（可直连 API，无需代理）+ 专用 QQ 小号。
> 架构：QQ ↔ **NapCat**（OneBot v11）↔ 反向 WebSocket ↔ **NoneBot2** ↔ 中转 API。

⚠️ 封号风险：NapCat 走非官方协议，**务必用小号**，别绑重要关系链。

---

## 一、准备（一次性）

```bash
# 1. 装 Python 3.11+（多数 VPS 自带，验证一下）
python3 --version

# 2. 拉取本目录到 VPS（或整个 liwenya_bot/，因为 persona 在上一层）
#    确保 VPS 上目录结构是：
#      liwenya_bot/
#        ├── liwenya_persona.txt   ← 插件会读这个
#        └── qqbot/                ← NoneBot2 项目
#            ├── bot.py
#            ├── requirements.txt
#            └── plugins/liwenya_chat.py

# 3. 建虚拟环境装依赖
cd liwenya_bot/qqbot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

---

## 二、配置 NoneBot2

```bash
cp .env.example .env
# 编辑 .env，重点填：
#   PORT=8080                 ← NapCat 待会要连这个端口
#   ONEBOT_ACCESS_TOKEN=xxx   ← 自己定一个随机串，两边要一致
#   SUPERUSERS=["你的QQ号"]
#   LIWENYA_API_KEY=...       ← 中转 API 密钥
#   LIWENYA_MODEL=...         ← 实际模型名
```

`.env` 里的 `LIWENYA_*` 与命令行脚本同名，可直接复用你已调好的那套值。

---

## 三、装并登录 NapCat

NapCat 推荐用官方一键脚本或 Docker。以 Docker 为例：

```bash
# 拉起 NapCat（示例，具体以 NapCat 官方文档为准）
docker run -d --name napcat --restart=always \
  -e NAPCAT_UID=$(id -u) -e NAPCAT_GID=$(id -g) \
  -p 3000:3000 -p 6099:6099 \
  -v $(pwd)/napcat/config:/app/napcat/config \
  -v $(pwd)/napcat/QQ:/app/.config/QQ \
  mlikiowa/napcat-docker:latest
```

首次启动看容器日志里的登录二维码 / 或用 WebUI（`http://VPS_IP:6099`）扫码登录**小号**。

### 关键：配置 OneBot 反向 WebSocket

在 NapCat 的 WebUI 或配置文件里，添加一个 **反向 WebSocket 客户端**，让 NapCat 主动连 NoneBot2：

- 地址：`ws://127.0.0.1:8080/onebot/v11/ws`
  （若 NapCat 在 Docker 里、NoneBot 在宿主机，用 `ws://172.17.0.1:8080/...` 或 host 网络）
- Token：填 `.env` 里的 `ONEBOT_ACCESS_TOKEN`

> NoneBot2 的 OneBot v11 适配器默认监听路径就是 `/onebot/v11/ws`。

---

## 四、启动 NoneBot2

```bash
cd liwenya_bot/qqbot
. .venv/bin/activate
python bot.py
```

看到日志里 NapCat 成功连入（`OneBot V11 | Bot xxx connected`）就通了。

### 验证链路
1. 用另一个 QQ 把小号拉进一个测试群；
2. 群里 **@小号 你好**；
3. 机器人应以李文亚口吻回复。私聊直接发消息也能触发。

---

## 五、常驻（systemd）

`python bot.py` 关终端就停。用 systemd 让它开机自启、崩溃重拉：

```ini
# /etc/systemd/system/liwenya-bot.service
[Unit]
Description=Liwenya QQ Bot (NoneBot2)
After=network-online.target

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/绝对路径/liwenya_bot/qqbot
ExecStart=/绝对路径/liwenya_bot/qqbot/.venv/bin/python bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now liwenya-bot
sudo journalctl -u liwenya-bot -f   # 看日志
```

NapCat 用 Docker 的 `--restart=always` 已能自愈。

---

## 六、使用与调优

| 场景 | 触发 |
|------|------|
| 群聊 | `@机器人 内容` |
| 私聊 | 直接发消息 |
| 清空上下文 | `@机器人 重置`（或 reset / 清空） |
| 退出角色 | 消息里含「退出 / 切回正常 / 不用演了」 |

控成本手段（都在 `.env` 里调）：
- `LIWENYA_MAX_TURNS` 上下文轮数，越小越省；
- `LIWENYA_COOLDOWN` 同会话冷却秒数，防刷；
- 只有被 @ / 私聊才调 API，普通群消息不花钱。

---

## 七、下一步（对应实施方案阶段 3–5）

- **阶段 3 Fandom 提醒**：复用本仓库 pywikibot，`apscheduler` 定时轮询
  `Special:RecentChanges` 推送到群。见 `QQ机器人实施方案.md`。
- **阶段 4 GitHub / B站提醒**、**阶段 5 群管**：按需加插件到 `plugins/`。
