"""为残缺条目挂 {{Stub}} 标记

给内容极短、结构缺失的「小作品」条目在页尾挂上 {{Stub}} 模板，
提示编者完善。安全设计：dry-run 默认；幂等（已挂则跳过）；不覆盖正文。

用法::
    .venv/bin/python tag_stubs.py            # 预览
    .venv/bin/python tag_stubs.py --execute  # 写入
"""
import argparse
import pywikibot

# 需挂 Stub 的残缺条目
STUB_ARTICLES = [
    '叶绿体无气孔论',
    '化学理论(未命名)',
    '文亚四定律',
    '地球翻滚运动',
]

STUB_TAG = '\n\n{{Stub}}'


def process(site, title, execute):
    page = pywikibot.Page(site, title)
    if not page.exists():
        print(f"  ⏭️  [[{title}]] 不存在，跳过")
        return 'skip'
    text = page.text
    if '{{Stub' in text or '{{stub' in text:
        print(f"  ✅ [[{title}]] 已有 Stub 标记，跳过")
        return 'skip'
    if not execute:
        print(f"  📝 [DRY-RUN] 将为 [[{title}]] 页尾添加 {{{{Stub}}}}")
        return 'plan'
    page.text = text.rstrip() + STUB_TAG + '\n'
    page.save(summary='标记为小作品（{{Stub}}），提示完善', bot=True)
    print(f"  🎉 已标记 [[{title}]]")
    return 'done'


def main():
    parser = argparse.ArgumentParser(description='为残缺条目挂 Stub 标记')
    parser.add_argument('--execute', action='store_true', help='真正写入（默认预览）')
    args = parser.parse_args()

    mode = '执行(EXECUTE)' if args.execute else '预览(DRY-RUN)'
    print(f"===== Stub 标记 [{mode}] =====")
    print("正在连接并登录 Fandom 站点...")
    site = pywikibot.Site('zh', 'fandom')
    site.login()
    print(f"✅ 已登录：{site.username()}\n")

    stats = {'plan': 0, 'done': 0, 'skip': 0}
    for title in STUB_ARTICLES:
        stats[process(site, title, args.execute)] += 1

    print("\n===== 汇总 =====")
    key = 'done' if args.execute else 'plan'
    print(f"  {'已标记' if args.execute else '计划标记'}：{stats[key]}  |  跳过：{stats['skip']}")


if __name__ == "__main__":
    main()
