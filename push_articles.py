"""推送 wiki 正文页面到线上

把 wiki_dump/articles/ 下的指定 *.wiki 文件推送为线上对应页面。
安全设计：dry-run 默认；内容一致则跳过；--execute 才写入。

用法::
    .venv/bin/python push_articles.py 教授列表 机构列表   # 预览指定页面
    .venv/bin/python push_articles.py --execute           # 推送全部（谨慎）
    .venv/bin/python push_articles.py 教授列表 --execute  # 推送指定页面
"""
import argparse
import os

import pywikibot

ARTICLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wiki_dump', 'articles')

DEFAULT_PAGES = [
    '教授列表',
    '机构列表',
    '学校列表',
    '概念列表',
    '事件',
]


def process(site, name, execute):
    filepath = os.path.join(ARTICLES_DIR, f'{name}.wiki')
    if not os.path.exists(filepath):
        print(f'  ✗ 文件不存在：{filepath}')
        return 'error'

    with open(filepath, encoding='utf-8') as f:
        text = f.read()

    page = pywikibot.Page(site, name)
    if page.exists() and page.text.strip() == text.strip():
        print(f'  ✅ [[{name}]] 内容一致，跳过')
        return 'skip'

    if not execute:
        action = '更新' if page.exists() else '创建'
        print(f'  📝 [DRY-RUN] 将{action}：[[{name}]]（{len(text)} 字符）')
        return 'plan'

    page.text = text
    page.save(summary='深色模式适配：硬编码调色盘改为 CSS 变量（v3.2.0）', bot=True)
    print(f'  🎉 已推送：[[{name}]]')
    return 'done'


def main():
    parser = argparse.ArgumentParser(description='推送 wiki 正文页面到线上')
    parser.add_argument('names', nargs='*', help='页面名（不含扩展名）；留空=默认列表')
    parser.add_argument('--execute', action='store_true', help='真正写入（默认预览）')
    args = parser.parse_args()

    names = args.names if args.names else DEFAULT_PAGES

    mode = '执行(EXECUTE)' if args.execute else '预览(DRY-RUN)'
    print(f'===== 正文推送 [{mode}] =====')
    print('正在连接并登录站点...')
    site = pywikibot.Site()
    site.login()
    print(f'✅ 已登录：{site.username()}\n')

    stats = {'plan': 0, 'done': 0, 'skip': 0, 'error': 0}
    for name in names:
        stats[process(site, name, args.execute)] += 1

    print('\n===== 汇总 =====')
    key = 'done' if args.execute else 'plan'
    print(f"  {'已推送' if args.execute else '计划推送'}：{stats[key]}  |  跳过：{stats['skip']}  |  错误：{stats['error']}")


if __name__ == '__main__':
    main()
