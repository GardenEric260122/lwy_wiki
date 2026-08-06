"""B站 API 访问层。故意不依赖 nonebot，可以单独跑自测：

    .venv/bin/python plugins/_bili_api.py 178757758

文件名以 _ 开头，nonebot 的 load_plugins 会跳过，不会被当成插件加载。

为什么是这套流程（2026-08 实测）：
- x/polymer/web-dynamic/v1/feed/space（动态流）已被整体封禁，带不带 Cookie、
  带不带合法 WBI 签名，一律 HTTP 412 request was banned，没有救。
- x/space/wbi/arc/search（投稿列表）可用，但要求三件事同时成立：
    1) buvid3/buvid4 是刚从 SPI 申请的（用久了、被标记过的指纹 → -352 风控校验失败）
    2) 该 buvid 经 ExClimbWuzhi 网关激活过（未激活 → 412）
    3) 请求带合法 WBI 签名（缺签名 → -352）
  少任何一条都拿不到数据。
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from functools import reduce

import httpx

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_SPI_API = "https://api.bilibili.com/x/frontend/finger/spi"
_ACTIVATE_API = "https://api.bilibili.com/x/internal/gaia-gateway/ExClimbWuzhi"
_NAV_API = "https://api.bilibili.com/x/web-interface/nav"
_ARC_SEARCH_API = "https://api.bilibili.com/x/space/wbi/arc/search"

# WBI 签名的字符重排表，B站前端硬编码的常量
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

# 会话有效期。WBI 密钥 B站每天轮换，buvid 指纹用久了会被标记，统一按小时级重建。
_SESSION_TTL = 6 * 3600

# 这些返回码都属于"指纹/签名不再被接受"，拿到就作废会话重建，重试才有意义
_BANNED_CODES = frozenset({-352, -401, -403, -412})

# 只从用户配的 Cookie 里挑登录态字段；指纹一律现申请，旧 buvid 会被风控标记
_LOGIN_KEYS = ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "sid")


class BiliBanned(RuntimeError):
    """被风控拦截。调用方应作废会话，下一轮用全新指纹重来。"""


def _base_headers() -> dict[str, str]:
    return {
        "User-Agent": _UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Origin": "https://space.bilibili.com",
        "Referer": "https://space.bilibili.com/",
    }


def _mixin_key(orig: str) -> str:
    return reduce(lambda s, i: s + orig[i], _MIXIN_KEY_ENC_TAB, "")[:32]


def _wbi_sign(params: dict, img_key: str, sub_key: str) -> dict:
    """给参数补上 wts 和 w_rid 两个签名字段。"""
    mixin = _mixin_key(img_key + sub_key)
    signed = dict(params, wts=int(time.time()))
    query = urllib.parse.urlencode(
        [
            (k, "".join(c for c in str(v) if c not in "!'()*"))
            for k, v in sorted(signed.items())
        ]
    )
    signed["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
    return signed


def login_cookie_parts(raw_cookie: str) -> str:
    """从配置的 Cookie 里只挑出登录态字段，丢掉 buvid 等指纹字段。

    带上旧 buvid 会直接触发 -352，所以这里必须过滤，不能整串透传。
    """
    parts: list[str] = []
    for chunk in raw_cookie.split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key, value = key.strip(), value.strip()
        if key in _LOGIN_KEYS and value:
            parts.append(f"{key}={value}")
    return "; ".join(parts)


def _activation_payload(buvid3: str) -> str:
    """ExClimbWuzhi 要求的浏览器环境上报体，字段名是 B站混淆后的固定 key。"""
    payload = {
        "3064": 1,
        "5062": str(int(time.time() * 1000)),
        "03bf": "https://space.bilibili.com/",
        "39c8": "333.999.fp.risk",
        "34f1": "",
        "d402": "",
        "654a": "",
        "6e7c": "1920x1080",
        "3c43": {
            "2673": 0, "5766": 24, "6527": 0, "7003": 1, "807e": 1,
            "b8ce": _UA, "641c": 0, "07a4": "zh-CN", "1c57": 8, "0bd0": 8,
            "748e": [1080, 1920], "d61f": [1040, 1920], "fc9d": -480,
            "6aa9": "Asia/Shanghai", "75b8": 1, "3b21": 1, "8a1c": 0,
            "d52f": "124.04347527516074", "adca": "Win32", "80c9": [],
            "1cb8": ["31", "0", "0"], "0ca4": "Windows",
        },
        "54ef": "{}",
        "8b94": "",
        "df35": buvid3,
        "07a4": "zh-CN",
        "5f45": None,
        "db46": 0,
    }
    return json.dumps({"payload": json.dumps(payload, separators=(",", ":"))})


class BiliSession:
    """持有一套"新申请 + 已激活"的设备指纹和 WBI 密钥，过期或被风控时自动重建。"""

    def __init__(self, login_cookie: str = "") -> None:
        self._login = login_cookie_parts(login_cookie)
        self._cookie = ""
        self._img_key = ""
        self._sub_key = ""
        self._born = 0.0

    @property
    def has_login(self) -> bool:
        return bool(self._login)

    @property
    def usable(self) -> bool:
        return bool(
            self._cookie
            and self._img_key
            and self._sub_key
            and time.time() - self._born < _SESSION_TTL
        )

    def invalidate(self) -> None:
        self._cookie = ""
        self._born = 0.0

    async def ensure(self, client: httpx.AsyncClient) -> None:
        """会话不可用时走完 申请指纹 → 激活 → 取 WBI 密钥 三步。"""
        if self.usable:
            return

        # 1) 申请全新 buvid3 / buvid4
        resp = await client.get(_SPI_API, headers=_base_headers(), timeout=15)
        resp.raise_for_status()
        spi = resp.json()
        if spi.get("code") != 0:
            raise RuntimeError(f"SPI 申请指纹失败 code={spi.get('code')}")
        data = spi.get("data") or {}
        buvid3, buvid4 = data.get("b_3", ""), data.get("b_4", "")
        if not buvid3 or not buvid4:
            raise RuntimeError("SPI 未返回 buvid3/buvid4")

        cookie = f"buvid3={buvid3}; buvid4={buvid4}; b_nut={int(time.time())}"
        if self._login:
            cookie = f"{cookie}; {self._login}"

        # 2) 激活指纹。不激活的话后面必然 412。
        resp = await client.post(
            _ACTIVATE_API,
            headers={
                **_base_headers(),
                "Cookie": cookie,
                "Content-Type": "application/json",
            },
            content=_activation_payload(buvid3),
            timeout=15,
        )
        if resp.status_code != 200 or resp.json().get("code") != 0:
            raise RuntimeError(
                f"指纹激活失败 http={resp.status_code} body={resp.text[:100]}"
            )

        # 3) 取 WBI 密钥对
        resp = await client.get(
            _NAV_API, headers={**_base_headers(), "Cookie": cookie}, timeout=15
        )
        resp.raise_for_status()
        wbi = (resp.json().get("data") or {}).get("wbi_img") or {}
        img_key = wbi.get("img_url", "").rsplit("/", 1)[-1].split(".")[0]
        sub_key = wbi.get("sub_url", "").rsplit("/", 1)[-1].split(".")[0]
        if not img_key or not sub_key:
            raise RuntimeError("nav 接口未返回 WBI 密钥")

        self._cookie, self._img_key, self._sub_key = cookie, img_key, sub_key
        self._born = time.time()

    async def fetch_videos(
        self, client: httpx.AsyncClient, uid: str, limit: int = 5
    ) -> tuple[str, list[dict]]:
        """返回 (UP主名, [{bvid, title}, ...])，按发布时间倒序，最多 limit 条。"""
        await self.ensure(client)

        params = _wbi_sign(
            {
                "mid": uid,
                "ps": limit,
                "pn": 1,
                "order": "pubdate",
                "platform": "web",
                "web_location": "1550101",
            },
            self._img_key,
            self._sub_key,
        )
        resp = await client.get(
            _ARC_SEARCH_API,
            params=params,
            headers={
                **_base_headers(),
                "Cookie": self._cookie,
                "Referer": f"https://space.bilibili.com/{uid}/video",
            },
            timeout=20,
        )

        if resp.status_code == 412:
            self.invalidate()
            raise BiliBanned("HTTP 412 request was banned")
        resp.raise_for_status()

        payload = resp.json()
        code = payload.get("code", -1)
        if code in _BANNED_CODES:
            self.invalidate()
            raise BiliBanned(f"code={code} {payload.get('message', '')}")
        if code != 0:
            raise RuntimeError(f"code={code} message={payload.get('message', '')}")

        vlist = ((payload.get("data") or {}).get("list") or {}).get("vlist") or []
        author = uid
        videos: list[dict] = []
        for item in vlist:
            bvid = item.get("bvid") or ""
            if not bvid:
                continue
            if author == uid and item.get("author"):
                author = item["author"]
            videos.append({"bvid": bvid, "title": item.get("title") or "?"})
            if len(videos) >= limit:
                break
        return author, videos


async def _selftest(uids: list[str]) -> int:
    """独立自测：拿真实配置跑一遍，打印每个 UID 的最新视频。"""
    import os
    from pathlib import Path

    cookie = os.environ.get("BILI_COOKIE", "")
    if not cookie:
        try:
            from dotenv import dotenv_values

            env_path = Path(__file__).resolve().parent.parent / ".env"
            cookie = (dotenv_values(env_path).get("BILI_COOKIE") or "").strip()
        except Exception:  # noqa: BLE001
            cookie = ""

    session = BiliSession(cookie)
    print(f"配置里的登录态字段：{'有' if session.has_login else '无（只用匿名指纹）'}")

    failed = 0
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for uid in uids:
            try:
                author, videos = await session.fetch_videos(client, uid)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"UID {uid}: 失败 {type(exc).__name__}: {exc}")
                continue
            head = videos[0] if videos else None
            print(
                f"UID {uid}: OK author={author} 拿到 {len(videos)} 条"
                + (f" 最新 {head['bvid']} 《{head['title'][:36]}》" if head else "")
            )
    return failed


if __name__ == "__main__":
    import asyncio
    import sys

    args = sys.argv[1:] or ["178757758"]
    sys.exit(1 if asyncio.run(_selftest(args)) else 0)
