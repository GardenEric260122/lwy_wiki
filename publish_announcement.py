"""公告与讨论页发布脚本

为本次「重定向规范化」改动创建：
  1. 机器人用户页        User:WenyaverseBot          —— 说明账号身份
  2. 操作公告页          文亚宇宙世界观 Wiki:机器人操作日志  —— 记录本次改动
  3. 对应讨论页          （上页 talk）              —— 供社区反馈

安全设计：默认 dry-run；--execute 才写入；已存在的页面跳过（不覆盖）。

用法::
    .venv/bin/python publish_announcement.py            # 干跑
    .venv/bin/python publish_announcement.py --execute  # 写入
"""
import argparse
import pywikibot

PROJECT = '文亚宇宙世界观 Wiki'
LOG_PAGE = f'{PROJECT}:机器人操作日志'
# 项目页的讨论页在命名空间上加 talk（ns5），而非标题后缀
TALK_PAGE = f'{PROJECT} talk:机器人操作日志'

USER_PAGE_TEXT = """\
{{Bot}}
本账号 '''WenyaverseBot''' 是由维护者操作的[[w:c:community:Help:机器人|机器人账号]]，
基于 [https://www.mediawiki.org/wiki/Manual:Pywikibot Pywikibot] 框架运行，
用于批量维护本 Wiki 的链接、分类与样式等重复性事务。

* 操作记录见：[[""" + LOG_PAGE + """]]
* 如对本机器人的编辑有疑问或建议，欢迎在 [[User talk:WenyaverseBot|讨论页]] 留言。

[[分类:机器人]]
"""

LOG_PAGE_TEXT = """\
本页记录 [[User:WenyaverseBot|WenyaverseBot]] 在本 Wiki 执行的自动化维护操作。

== 2026-07-27：重定向规范化（消除分裂红链）==

=== 背景 ===
本 Wiki 中，同一人物常存在「带／不带『教授』」两种链接写法（例如
<code><nowiki>[[孙笑川]]</nowiki></code> 与 <code><nowiki>[[孙笑川教授]]</nowiki></code>），
导致引用被拆分、部分写法指向红链，影响条目互联与导航。

=== 本次改动 ===
创建了以下 6 个'''重定向页''',将异写统一指向正式条目：

{| class="wikitable"
! 重定向源 !! 指向目标 !! 说明
|-
| [[孙笑川]] || [[孙笑川教授]] || 去「教授」异写
|-
| [[卢初雪]] || [[卢初雪教授]] || 去「教授」异写
|-
| [[卢德霜]] || [[卢德霜教授]] || 去「教授」异写
|-
| [[侯国玉]] || [[侯国玉教授]] || 去「教授」异写
|-
| [[关瑞生]] || [[关瑞生教授]] || 去「教授」异写
|-
| [[李文亚教授]] || [[李文亚]] || 反向：主条目名不含「教授」
|}

=== 影响 ===
* 上述异写链接现在都能正确跳转到目标条目，不再产生红链。
* 仅新建重定向页，'''未修改任何现有条目的正文内容'''。

=== 后续计划 ===
经镜像快照扫描，本 Wiki 仍存在可优化项，将在征求社区意见后分批处理：
* 约 50 篇条目缺少分类，拟批量补充分类体系；
* 生成「待创建条目」清单（红链约 200 项，按被引次数排序）；
* 清理误用全角冒号的错误命名空间页（如 <code>Template：Event</code>）。

如有意见或建议，欢迎前往 [[""" + TALK_PAGE + """|本页讨论页]] 讨论。

~~~~
"""

TALK_PAGE_TEXT = """\
== 关于机器人自动化维护的讨论 ==

本页用于讨论 [[User:WenyaverseBot|WenyaverseBot]] 的自动化维护操作。

首次操作（2026-07-27 的重定向规范化）详情见 [[""" + LOG_PAGE + """|操作日志]]。
对以下事项欢迎发表意见：

* 重定向命名规范（是否统一为「XX教授」形式？）；
* 分类体系设计（人物／机构／理论／事件等如何划分）；
* 是否同意机器人批量补充分类、生成待创建清单等后续操作。

请在下方签名留言（<code><nowiki>~~~~</nowiki></code>）：

~~~~
"""

PAGES = [
    ('User:WenyaverseBot', USER_PAGE_TEXT, '创建机器人用户页'),
    (LOG_PAGE, LOG_PAGE_TEXT, '创建机器人操作日志：记录重定向规范化改动'),
    (TALK_PAGE, TALK_PAGE_TEXT, '创建讨论页：征求社区对自动化维护的意见'),
]


def process(site, title, text, summary, execute):
    page = pywikibot.Page(site, title)
    if page.exists():
        print(f"  ⏭️  [[{title}]] 已存在，跳过（不覆盖）")
        return 'skip'
    if not execute:
        print(f"  📝 [DRY-RUN] 将创建：[[{title}]]（{len(text)} 字符）")
        return 'plan'
    page.text = text
    page.save(summary=summary, bot=True)
    print(f"  🎉 已创建：[[{title}]]")
    return 'done'


def main():
    parser = argparse.ArgumentParser(description='发布公告与讨论页')
    parser.add_argument('--execute', action='store_true', help='真正写入（默认干跑）')
    args = parser.parse_args()

    mode = '执行(EXECUTE)' if args.execute else '干跑(DRY-RUN)'
    print(f"===== 公告发布脚本 [{mode}] =====")
    print("正在连接并登录 Fandom 站点...")
    site = pywikibot.Site('zh', 'fandom')
    site.login()
    print(f"✅ 已登录：{site.username()}\n")

    stats = {'plan': 0, 'done': 0, 'skip': 0}
    for title, text, summary in PAGES:
        stats[process(site, title, text, summary, args.execute)] += 1

    print("\n===== 汇总 =====")
    if args.execute:
        print(f"  已创建：{stats['done']}  |  跳过：{stats['skip']}")
    else:
        print(f"  计划创建：{stats['plan']}  |  跳过：{stats['skip']}")
        print("  （干跑未写入，确认后加 --execute）")


if __name__ == "__main__":
    main()
