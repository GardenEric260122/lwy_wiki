"""Wiki 内容与设置抓取脚本

将文亚宇宙世界观 Wiki 的以下内容抓取到本地 wiki_dump/ 目录，便于离线
分析编写风格与样式：

  wiki_dump/
  ├── siteinfo.json           站点配置（命名空间、扩展、版本等）
  ├── mediawiki/              MediaWiki 界面页（含 Common.css 等实时样式）
  ├── templates/              模板源码（*.wiki）
  ├── articles/              条目正文（*.wiki）
  └── categories.txt          分类列表

用法::

    .venv/bin/python fetch_wiki_content.py

前提：Clash Verge 代理开启；凭据有效。
"""
import json
import os

import pywikibot

DUMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wiki_dump')


def _safe_name(title):
    """把页面标题转成安全的文件名。"""
    return title.replace('/', '__').replace(':', '_').replace(' ', '_')


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def dump_siteinfo(site):
    print("📊 抓取站点配置 siteinfo...")
    info = {
        'sitename': site.sitename,
        'lang': site.lang,
        'mediawiki_version': site.version(),
        'namespaces': {str(k): v.custom_name for k, v in site.namespaces.items() if k >= 0},
    }
    _write(os.path.join(DUMP_DIR, 'siteinfo.json'),
           json.dumps(info, ensure_ascii=False, indent=2))
    print(f"   → siteinfo.json（MediaWiki {info['mediawiki_version']}）")


def dump_namespace(site, ns_id, subdir, suffix='.wiki', limit=None):
    print(f"📥 抓取命名空间 ns{ns_id} → {subdir}/ ...")
    count = 0
    for page in site.allpages(namespace=ns_id, total=limit):
        try:
            text = page.text
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠️ 跳过 {page.title()}: {e}")
            continue
        fname = _safe_name(page.title(with_ns=False)) + suffix
        _write(os.path.join(DUMP_DIR, subdir, fname), text)
        count += 1
    print(f"   → 共 {count} 页")
    return count


def dump_mediawiki_ui(site):
    """MediaWiki 命名空间：保留原后缀（.css/.js），其余存为 .txt。"""
    print("📥 抓取 MediaWiki 界面页 → mediawiki/ ...")
    count = 0
    for page in site.allpages(namespace=8, total=None):
        title = page.title(with_ns=False)
        try:
            text = page.text
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠️ 跳过 {title}: {e}")
            continue
        if title.endswith(('.css', '.js')):
            fname = _safe_name(title)
        else:
            fname = _safe_name(title) + '.txt'
        _write(os.path.join(DUMP_DIR, 'mediawiki', fname), text)
        count += 1
    print(f"   → 共 {count} 页")
    return count


def dump_categories(site):
    print("📥 抓取分类列表 → categories.txt ...")
    lines = [cat.title() for cat in site.allcategories(total=None)]
    _write(os.path.join(DUMP_DIR, 'categories.txt'), '\n'.join(lines) + '\n')
    print(f"   → 共 {len(lines)} 个分类")


def main():
    print("正在连接并登录 Fandom 站点...")
    site = pywikibot.Site('zh', 'fandom')
    site.login()
    print(f"✅ 已登录：{site.username()}\n")

    dump_siteinfo(site)
    dump_mediawiki_ui(site)              # 含实时 Common.css
    dump_namespace(site, 10, 'templates')   # 模板
    dump_namespace(site, 0, 'articles')     # 条目
    dump_categories(site)

    print(f"\n🎉 抓取完成，全部内容已保存到：{DUMP_DIR}")


if __name__ == "__main__":
    main()
