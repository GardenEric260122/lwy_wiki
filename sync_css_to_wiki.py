"""CSS 同步脚本：将本地 common.css 推送到线上 MediaWiki:Common.css

把 styles/common.css 的内容更新到线上 [[MediaWiki:Common.css]]，
使仓库源文件与线上部署保持一致。

安全设计：
  - 默认 dry-run：只显示本地与线上的差异，不写入；
  - --execute 才真正保存；
  - 若线上内容与本地已一致 → 跳过（幂等）。

用法::
    .venv/bin/python sync_css_to_wiki.py            # 预览差异
    .venv/bin/python sync_css_to_wiki.py --execute  # 推送到线上

前提：Clash Verge 代理开启（本地）；凭据有效。
"""
import argparse
import difflib
import os

import pywikibot

CSS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'styles', 'common.css')
TARGET_PAGE = 'MediaWiki:Common.css'


def read_local_version(text):
    import re
    m = re.search(r'--wy-css-version:\s*"([\d.]+)"', text)
    return m.group(1) if m else '?'


def main():
    parser = argparse.ArgumentParser(description='同步 common.css 到线上 MediaWiki:Common.css')
    parser.add_argument('--execute', action='store_true', help='真正推送（默认仅预览差异）')
    args = parser.parse_args()

    with open(CSS_FILE, encoding='utf-8') as f:
        local_text = f.read()
    local_ver = read_local_version(local_text)

    mode = '执行(EXECUTE)' if args.execute else '预览(DRY-RUN)'
    print(f"===== CSS 同步 [{mode}] =====")
    print(f"本地 common.css 版本：{local_ver}")

    print("正在连接并登录 Fandom 站点...")
    site = pywikibot.Site('zh', 'fandom')
    site.login()
    print(f"✅ 已登录：{site.username()}")

    page = pywikibot.Page(site, TARGET_PAGE)
    online_text = page.text if page.exists() else ''

    if online_text == local_text:
        print("\nℹ️ 线上内容与本地一致，无需同步。")
        return

    # 展示差异摘要
    diff = list(difflib.unified_diff(
        online_text.splitlines(), local_text.splitlines(),
        fromfile='线上 MediaWiki:Common.css', tofile='本地 common.css', lineterm='',
    ))
    added = sum(1 for d in diff if d.startswith('+') and not d.startswith('+++'))
    removed = sum(1 for d in diff if d.startswith('-') and not d.startswith('---'))
    print(f"\n📊 差异：线上将 +{added} / -{removed} 行")
    print("--- 差异预览（前 40 行）---")
    for line in diff[:40]:
        print(line)
    if len(diff) > 40:
        print(f"... 省略 {len(diff) - 40} 行")

    if not args.execute:
        print("\n[预览] 未写入。确认无误后加 --execute 推送到线上。")
        return

    page.text = local_text
    page.save(summary=f'同步桌面样式表至 v{local_ver}（来自仓库 styles/common.css）', bot=True)
    print(f"\n🎉 已推送到线上 [[{TARGET_PAGE}]]（v{local_ver}）")
    print("   请在浏览器 Ctrl/Cmd+Shift+R 清缓存后核对效果。")


if __name__ == "__main__":
    main()
