"""上传模板到 Wiki

把 wiki_templates/ 下的 *.wiki 文件上传为线上 Template:<文件名> 页面。
安全设计：dry-run 默认；已存在且内容一致则跳过；--force 才覆盖已存在页面。

用法::
    .venv/bin/python upload_templates.py                    # 预览全部
    .venv/bin/python upload_templates.py Theory --execute   # 上传指定模板
    .venv/bin/python upload_templates.py --execute          # 上传全部（不覆盖已存在）
"""
import argparse
import os
import glob

import pywikibot

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wiki_templates')


def process(site, filepath, execute, force):
    name = os.path.splitext(os.path.basename(filepath))[0]
    title = f'Template:{name}'
    with open(filepath, encoding='utf-8') as f:
        text = f.read()

    page = pywikibot.Page(site, title)
    if page.exists():
        if page.text.strip() == text.strip():
            print(f"  ✅ [[{title}]] 已存在且内容一致，跳过")
            return 'skip'
        if not force:
            print(f"  ⚠️  [[{title}]] 已存在但内容不同，跳过（加 --force 才覆盖）")
            return 'skip'

    if not execute:
        action = '覆盖' if page.exists() else '创建'
        print(f"  📝 [DRY-RUN] 将{action}：[[{title}]]（{len(text)} 字符）")
        return 'plan'

    page.text = text
    summary = '更新模板' if page.exists() else '创建模板'
    page.save(summary=f'{summary}（来自仓库 wiki_templates/）', bot=True)
    print(f"  🎉 已上传：[[{title}]]")
    return 'done'


def main():
    parser = argparse.ArgumentParser(description='上传模板到 Wiki')
    parser.add_argument('names', nargs='*', help='指定模板名（不含扩展名）；留空=全部')
    parser.add_argument('--execute', action='store_true', help='真正写入（默认预览）')
    parser.add_argument('--force', action='store_true', help='覆盖已存在且内容不同的模板')
    args = parser.parse_args()

    if args.names:
        files = [os.path.join(TEMPLATE_DIR, f'{n}.wiki') for n in args.names]
    else:
        files = sorted(glob.glob(os.path.join(TEMPLATE_DIR, '*.wiki')))

    mode = '执行(EXECUTE)' if args.execute else '预览(DRY-RUN)'
    print(f"===== 模板上传 [{mode}] =====")
    print("正在连接并登录 Fandom 站点...")
    site = pywikibot.Site('zh', 'fandom')
    site.login()
    print(f"✅ 已登录：{site.username()}\n")

    stats = {'plan': 0, 'done': 0, 'skip': 0}
    for fp in files:
        if not os.path.exists(fp):
            print(f"  ✗ 文件不存在：{fp}")
            continue
        stats[process(site, fp, args.execute, args.force)] += 1

    print("\n===== 汇总 =====")
    key = 'done' if args.execute else 'plan'
    print(f"  {'已上传' if args.execute else '计划上传'}：{stats[key]}  |  跳过：{stats['skip']}")


if __name__ == "__main__":
    main()
