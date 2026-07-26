"""重定向创建脚本

为「同一实体的不同链接写法」批量创建重定向页，消除因命名不统一
（带/不带「教授」等）导致的分裂红链。

安全设计：
  - 默认 **dry-run**（只打印计划，不写入）；加 --execute 才真正创建。
  - 幂等：目标页已存在且已是指向正确的重定向 → 跳过。
  - 绝不覆盖：若源页已存在且**不是**重定向（即已有正文内容）→ 跳过并告警。
  - --limit N 限制本次处理条数，便于小批量验证。

用法::

    # 干跑（默认，安全）
    .venv/bin/python create_redirects.py

    # 小批量验证：只真正创建前 2 条
    .venv/bin/python create_redirects.py --execute --limit 2

    # 全量执行
    .venv/bin/python create_redirects.py --execute

前提：Clash Verge 代理开启；凭据有效。
"""
import argparse
import pywikibot

# 重定向映射：源页标题 -> 目标页标题
# 源为红链异写，目标为已存在的正式条目
REDIRECTS = {
    '孙笑川': '孙笑川教授',
    '卢初雪': '卢初雪教授',
    '卢德霜': '卢德霜教授',
    '侯国玉': '侯国玉教授',
    '关瑞生': '关瑞生教授',
    '李文亚教授': '李文亚',   # 反向特例：条目名不含「教授」
}


def process(site, source, target, execute):
    src_page = pywikibot.Page(site, source)
    tgt_page = pywikibot.Page(site, target)

    # 目标必须存在，否则重定向会指向红链，无意义
    if not tgt_page.exists():
        print(f"  ⏭️  跳过 [[{source}]]：目标 [[{target}]] 不存在")
        return 'skip'

    if src_page.exists():
        if src_page.isRedirectPage():
            try:
                cur = src_page.getRedirectTarget().title()
            except Exception:  # noqa: BLE001
                cur = '?'
            if cur == tgt_page.title():
                print(f"  ✅ 已存在且正确：[[{source}]] → [[{target}]]，跳过")
                return 'skip'
            print(f"  ⚠️  [[{source}]] 已是重定向但指向 [[{cur}]]（≠目标），跳过（不擅自改向）")
            return 'skip'
        # 源页存在且是正文内容 —— 绝不覆盖
        print(f"  ⛔ [[{source}]] 已存在且含正文内容，跳过（不覆盖）")
        return 'skip'

    # 需要创建
    redirect_text = f"#REDIRECT [[{target}]]"
    if not execute:
        print(f"  📝 [DRY-RUN] 将创建：[[{source}]] → [[{target}]]")
        return 'plan'

    src_page.text = redirect_text
    src_page.save(summary=f'创建重定向 → [[{target}]]（规范化链接写法）', bot=True)
    print(f"  🎉 已创建：[[{source}]] → [[{target}]]")
    return 'done'


def main():
    parser = argparse.ArgumentParser(description='批量创建重定向页')
    parser.add_argument('--execute', action='store_true', help='真正写入（默认仅干跑）')
    parser.add_argument('--limit', type=int, default=0, help='最多处理条数（0=不限）')
    args = parser.parse_args()

    mode = '执行(EXECUTE)' if args.execute else '干跑(DRY-RUN)'
    print(f"===== 重定向脚本 [{mode}] =====")
    if args.limit:
        print(f"（限量：最多 {args.limit} 条）")

    print("正在连接并登录 Fandom 站点...")
    site = pywikibot.Site('zh', 'fandom')
    site.login()
    print(f"✅ 已登录：{site.username()}\n")

    stats = {'plan': 0, 'done': 0, 'skip': 0}
    processed = 0
    for source, target in REDIRECTS.items():
        if args.limit and processed >= args.limit:
            print(f"\n（已达限量 {args.limit}，停止）")
            break
        result = process(site, source, target, args.execute)
        stats[result] = stats.get(result, 0) + 1
        if result in ('plan', 'done'):
            processed += 1

    print("\n===== 汇总 =====")
    if args.execute:
        print(f"  已创建：{stats['done']}  |  跳过：{stats['skip']}")
    else:
        print(f"  计划创建：{stats['plan']}  |  跳过：{stats['skip']}")
        print("  （这是干跑，未写入。确认无误后加 --execute 执行）")


if __name__ == "__main__":
    main()
