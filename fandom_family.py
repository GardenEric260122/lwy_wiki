"""Pywikibot family file for the Wenyaverse Fandom wiki.

由手工编写而非 generate_family_file 自动生成，
因为 Fandom 会拦截默认 UA 的站点探测请求（返回 403）。
"""
from pywikibot import family


class Family(family.Family):  # noqa: D101
    name = 'fandom'
    langs = {
        'zh': 'wenyaverse.fandom.com',
    }

    def scriptpath(self, code):
        # 文亚宇宙 Wiki 的 api.php / index.php 位于 /zh 语言路径下
        return '/zh'

    def protocol(self, code):
        return 'https'
