"""CSS 语义化版本发布脚本

用于 李文亚Wiki/wiki2.css 的版本管理：
  1. 读取当前版本号；
  2. 分析 git diff，**建议** major/minor/patch 升级级别（非强制）；
  3. 由你确认或指定级别，自动更新三处版本号（Banner、--wy-css-version、Changelog）；
  4. 归档为 archive/wiki2-vX.Y.Z.css；
  5. 打印后续 git commit + tag 命令（不自动 push）。

SemVer 判定规则（基于 diff）：
  - MAJOR：删除/重命名 --wy-* 变量，或删除/修改现有选择器（破坏性）
  - MINOR：仅新增 class / 变量 / 规则（向后兼容）
  - PATCH：仅改色值 / 数值 / 注释等

用法::
    # 预览建议（默认，不改文件）
    .venv/bin/python bump_css_version.py

    # 指定级别并写入
    .venv/bin/python bump_css_version.py --level minor --execute
"""
import argparse
import os
import re
import shutil
import subprocess

CSS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '李文亚Wiki')
CSS_FILE = os.path.join(CSS_DIR, 'wiki2.css')
ARCHIVE_DIR = os.path.join(CSS_DIR, 'archive')


def read_version(text):
    m = re.search(r'--wy-css-version:\s*"([\d.]+)"', text)
    return m.group(1) if m else None


def bump(version, level):
    major, minor, patch = (int(x) for x in version.split('.'))
    if level == 'major':
        return f'{major + 1}.0.0'
    if level == 'minor':
        return f'{major}.{minor + 1}.0'
    return f'{major}.{minor}.{patch + 1}'


def git_diff():
    """返回 wiki2.css 相对 HEAD 的 diff 文本（未提交改动）。"""
    try:
        return subprocess.run(
            ['git', 'diff', 'HEAD', '--', CSS_FILE],
            capture_output=True, text=True, cwd=os.path.dirname(CSS_DIR),
        ).stdout
    except Exception:  # noqa: BLE001
        return ''


def suggest_level(diff):
    """依据 diff 建议升级级别，返回 (level, reason)。"""
    removed = [ln[1:] for ln in diff.splitlines() if ln.startswith('-') and not ln.startswith('---')]
    added = [ln[1:] for ln in diff.splitlines() if ln.startswith('+') and not ln.startswith('+++')]

    # 破坏性：删除/改动了 --wy-* 变量定义或现有选择器
    removed_vars = [ln for ln in removed if re.search(r'--wy-[\w-]+\s*:', ln)]
    removed_selectors = [ln for ln in removed if re.match(r'\s*[.#]?[\w.\-#>: ]+\{', ln)]
    if removed_vars or removed_selectors:
        return 'major', f'检测到删除/修改现有变量({len(removed_vars)})或选择器({len(removed_selectors)})，可能破坏兼容'

    # 新增：出现新的 class / 变量 / 选择器
    added_selectors = [ln for ln in added if re.match(r'\s*[.#][\w.\-#>: ]+\{', ln)]
    added_vars = [ln for ln in added if re.search(r'--wy-[\w-]+\s*:', ln)]
    if added_selectors or added_vars:
        return 'minor', f'检测到新增选择器({len(added_selectors)})或变量({len(added_vars)})，向后兼容'

    # 其余视为小修补
    if added or removed:
        return 'patch', '仅检测到色值/数值/注释等小改动'
    return 'patch', '未检测到改动（或全部已提交）'


def update_versions(text, new_version):
    text = re.sub(r'(--wy-css-version:\s*")[\d.]+(")', rf'\g<1>{new_version}\g<2>', text)
    text = re.sub(r'(\*\s*版本：)[\d.]+', rf'\g<1>{new_version}', text)
    return text


def main():
    parser = argparse.ArgumentParser(description='CSS 语义化版本发布')
    parser.add_argument('--level', choices=['major', 'minor', 'patch'],
                        help='升级级别（不填则仅打印建议）')
    parser.add_argument('--execute', action='store_true', help='真正写入（默认预览）')
    args = parser.parse_args()

    with open(CSS_FILE, encoding='utf-8') as f:
        text = f.read()

    cur = read_version(text)
    print(f"当前版本：{cur}")

    diff = git_diff()
    level, reason = suggest_level(diff)
    print(f"\n📊 diff 分析建议级别：**{level.upper()}**")
    print(f"   理由：{reason}")

    chosen = args.level or level
    if not args.level:
        print(f"\n（未用 --level 指定，采用建议级别 {chosen}；如需更改请加 --level major|minor|patch）")

    new_version = bump(cur, chosen)
    print(f"\n版本变更：{cur} → {new_version}（{chosen}）")

    if not args.execute:
        print("\n[预览] 未写入。确认无误后加 --execute 执行。")
        return

    # 写入新版本号
    new_text = update_versions(text, new_version)
    with open(CSS_FILE, 'w', encoding='utf-8') as f:
        f.write(new_text)
    print(f"✅ 已更新 wiki2.css 版本号 → {new_version}")

    # 归档
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    archive_path = os.path.join(ARCHIVE_DIR, f'wiki2-v{new_version}.css')
    shutil.copy2(CSS_FILE, archive_path)
    print(f"✅ 已归档 → archive/wiki2-v{new_version}.css")

    print("\n下一步（请手动执行，确认无误后再 push）：")
    print("  1) 在 wiki2.css 顶部补写本版 Changelog 条目")
    print(f"  2) git add 李文亚Wiki/ && git commit -m 'feat(css): release wiki2 v{new_version}'")
    print(f"  3) git tag -a v{new_version} -m 'Release v{new_version}' && git push && git push --tags")
    print(f"  4) 将 wiki2.css 内容粘贴回线上 MediaWiki:Common.css，保持同步")


if __name__ == "__main__":
    main()
