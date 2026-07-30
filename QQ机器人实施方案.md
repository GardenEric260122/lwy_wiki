# QQ 机器人「李文亚」实施方案

> 目标：QQ 机器人，以李文亚教授风格对话 + 群聊管理 + B站/GitHub/Fandom 提醒。
> 已定方案：**VPS 部署 · Claude API · 优先做风格对话**。

---

## 一、技术栈（推荐）

| 层 | 选型 | 理由 |
|----|------|------|
| QQ 协议端 | **NapCat**（基于 NTQQ） | 目前最稳的非官方协议端，OneBot v11 标准 |
| 机器人框架 | **NoneBot2**（Python） | 与现有脚本同语言；插件生态最全 |
| 对话大脑 | **Claude API**（`claude-sonnet-5`） | 与现有 liwenya-perspective skill 无缝衔接 |
| 部署 | **VPS**（1–2核2G 起） | 7×24 稳定；建议境外或支持代理的节点 |

**数据流**：QQ ↔ NapCat ↔（OneBot v11 WebSocket）↔ NoneBot2 ↔ Claude API / 各平台 API

---

## 二、复用现有资产（重要优势）

1. **人格层**：`.claude/skills/liwenya-perspective/`（3347 行）
   - `SKILL.md` 的角色规则 → 作为 Claude 的 **system prompt**
   - `references/research/*.md`（表达DNA、决策启发式、语料）→ 作为背景知识/few-shot 示例
   - 这是本项目最大的差异化优势，别人复制不了。
2. **Fandom 提醒**：直接复用现有 pywikibot 基建
   - `site.recentchanges()` 轮询最近变更 → 推送到群
   - 登录、代理、family 配置全部现成。

---

## 三、分阶段实施（MVP 先行）

### 阶段 0：环境准备（VPS）
- 购置 VPS，装 Python 3.11+、NapCat、NoneBot2
- 准备**专用 QQ 小号**（⚠️ 见风险提示，勿用主号）
- 准备 Claude API key

### 阶段 1：跑通收发消息
- NapCat 登录 QQ 小号，配置 OneBot v11 WebSocket
- NoneBot2 连上 NapCat，实现「@机器人→回声」验证链路

### 阶段 2：李文亚风格对话（**优先，核心亮点**）
- 写一个 NoneBot2 插件 `liwenya_chat`：
  - 触发：群内 @机器人 或私聊
  - system prompt = `SKILL.md` 角色规则
  - 注入 `references/` 精选片段作为风格锚点
  - 调 Claude API（`claude-sonnet-5`），带**多轮上下文**（每用户/每群独立会话，限长度控成本）
  - 普通群消息不触发，省 token
- 调优：温度略高保持"暴躁"语气；加"退出角色"指令

### 阶段 3：Fandom 提醒（**最快见效，复用现有代码**）
- 定时任务（NoneBot2 的 `apscheduler`）轮询 `Special:RecentChanges`
- 记录上次检查的时间戳，只推新变更到指定群
- 消息可用李文亚口吻包装（"又有人动我的 Wiki！哪个单位的？"）

### 阶段 4：GitHub / B站 提醒
- **GitHub**：官方 API 轮询 repo 的 commits/issues/releases（或配 Webhook 更实时）
- **B站**：第三方 API 轮询 UP 主动态/开播（社区有 `nonebot-plugin-bilibili` 类插件）

### 阶段 5：群聊管理
- 入群欢迎、关键词/广告过滤、禁言、定时提醒、签到
- 可套李文亚人格（踢人时用他的口吻）
- 多数有现成 NoneBot2 插件，按需启用

---

## 四、关键配置与成本

- **Claude API 成本**：按对话量计。控制手段：仅 @/私聊触发、限上下文轮数、群聊冷却。
- **代理**：VPS 若在境外则直连 Claude；若在国内需配代理（同现有 Clash 思路）。
- **敏感信息**：QQ 账号、API key、各平台 token → 用环境变量或 `.env`，**勿入库**。

---

## 五、⚠️ 风险提示（务必知晓）

1. **封号风险**：NapCat 基于非官方 NTQQ 协议，腾讯可能封号。
   → **必须用小号**，不要用主 QQ；重要关系链勿绑定。
2. **合规**：如需完全合规，只能用腾讯官方 QQ 机器人平台，但群聊能力受限、审核严。
3. **B站 API** 易变、部分需登录态，是三个提醒源里最不稳的一环，做好维护预期。
4. **人格内容边界**：李文亚风格含攻击性语气，群内使用注意不要触发平台/群规风控。

---

## 六、下一步

本方案落地需在**独立代码库**进行（不混入本 Wiki 仓库）。建议：
1. 先在 VPS 完成阶段 0–1（环境+收发验证）；
2. 阶段 2 的人格插件可由我协助编写——把本仓库的 `liwenya-perspective` 资料
   转成 system prompt + 语料的具体实现。

> 需要时，我可以先帮你写出**阶段 2 的核心代码骨架**（NoneBot2 插件 + Claude 调用 +
> 人格 prompt 组装），你在 VPS 跑通阶段 1 后即可接入。
