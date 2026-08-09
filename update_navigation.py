"""导航栏同步脚本：将本地 Wiki-navigation.txt 推送到线上 MediaWiki:Wiki-navigation

用法::
    .venv/bin/python update_navigation.py            # 预览差异
    .venv/bin/python update_navigation.py --execute  # 推送到线上

前提：Clash Verge 代理开启（本地）；凭据有账号管理员权限。
"""
import argparse
import difflib
import os

import pywikibot

NAV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'wiki_dump', 'mediawiki', 'Wiki-navigation.txt')
TARGET_PAGE = 'MediaWiki:Wiki-navigation'


def main():
    parser = argparse.ArgumentParser(description='同步 Wiki-navigation.txt 到线上')
    parser.add_argument('--execute', action='store_true', help='真正推送（默认仅预览差异）')
    args = parser.parse_args()

    with open(NAV_FILE, encoding='utf-8') as f:
        local_text = f.read()

    mode = '执行(EXECUTE)' if args.execute else '预览(DRY-RUN)'
    print(f"===== 导航栏同步 [{mode}] =====")

    print("正在连接并登录 Fandom 站点...")
    site = pywikibot.Site('zh', 'fandom')
    site.login()
    print(f"✅ 已登录：{site.username()}")

    page = pywikibot.Page(site, TARGET_PAGE)
    online_text = page.text if page.exists() else ''

    if online_text.strip() == local_text.strip():
        print("\nℹ️ 线上内容与本地一致，无需同步。")
        return

    diff = list(difflib.unified_diff(
        online_text.splitlines(), local_text.splitlines(),
        fromfile=f'线上 {TARGET_PAGE}', tofile='本地 Wiki-navigation.txt', lineterm='',
    ))
    added = sum(1 for d in diff if d.startswith('+') and not d.startswith('+++'))
    removed = sum(1 for d in diff if d.startswith('-') and not d.startswith('---'))
    print(f"\n📊 差异：线上将 +{added} / -{removed} 行")
    for line in diff:
        print(line)

    if not args.execute:
        print("\n[预览] 未写入。确认无误后加 --execute 推送到线上。")
        return

    page.text = local_text
    page.save(summary='修复分类下拉框：将 #category1#/#category2# 替换为显式分类链接', bot=True)
    print(f"\n🎉 已推送到线上 [[{TARGET_PAGE}]]")
    print("   刷新主页后分类下拉框应显示：人物 / 理论 / 机构 / 大学 / 事件")


if __name__ == "__main__":
    main()
