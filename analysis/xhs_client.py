"""小红书 API 客户端 -- 评论抓取、笔记解析、搜索

封装小红书 Web API，支持：
    - resolve_note_id   解析小红书链接（短链/长链）
    - fetch_note_info   获取笔记详情
    - fetch_comments    获取评论（含子评论、翻页）
    - search_notes      搜索笔记
    - to_standard_comments  转换评论为标准格式

使用 Python 标准库（urllib、json、hashlib）+ xhs_sign.py 签名。

环境变量 / cookies_xhs.txt：
    XHS_COOKIES        整体 Cookie 字符串（格式：a1=xxx; web_session=xxx; ...）
    XHS_A1             a1 cookie（必需）
    XHS_WEB_SESSION    web_session cookie（必需）
    XHS_WEB_ID         webId cookie（可选）
    XHS_XSECAPPID      xsecappid cookie（可选）
    XHS_AB_REQUEST_ID  abRequestId cookie（可选）
    XHS_ACW_TC         acw_tc cookie（可选）
"""
from __future__ import annotations

import json
import hashlib
import logging
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, urlparse, parse_qs

from . import xhs_sign
from . import xhs_login

logger = logging.getLogger("xhs_client")

# ============================================================
# 路径常量
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

# ============================================================
# 请求头模板
# ============================================================

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

XHS_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Origin": "https://www.xiaohongshu.com",
    "Referer": "https://www.xiaohongshu.com/",
    "Content-Type": "application/json;charset=UTF-8",
}

# ============================================================
# Cookie 管理
# ============================================================

_cookies_cache: dict[str, str] | None = None


def load_xhs_cookies() -> dict[str, str]:
    """从环境变量或 cookies_xhs.txt 加载小红书 Cookie。

    支持两种环境变量方式：
    1. 整体变量 XHS_COOKIES：格式为 "a1=xxx; web_session=xxx; webId=xxx"
       （与 HTTP Cookie 头格式一致，适合 Railway 等云平台一键配置）
    2. 单独变量：XHS_A1 / XHS_WEB_SESSION / XHS_WEB_ID / XHS_XSECAPPID /
       XHS_AB_REQUEST_ID / XHS_ACW_TC

    优先级：单独环境变量 > XHS_COOKIES > cookies_xhs.txt

    Returns:
        Cookie 字典，如 {"a1": "xxx", "web_session": "xxx", "webId": "xxx"}
    """
    global _cookies_cache
    if _cookies_cache is not None:
        return _cookies_cache

    cookies: dict[str, str] = {}

    # 方式1：从 XHS_COOKIES 整体变量读取（格式：a1=xxx; web_session=xxx; ...）
    xhs_cookies_str = os.environ.get("XHS_COOKIES", "").strip()
    if xhs_cookies_str:
        for pair in xhs_cookies_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, _, value = pair.partition("=")
                key = key.strip()
                value = value.strip()
                if key and value:
                    cookies[key] = value
        logger.info(f"从 XHS_COOKIES 环境变量加载 {len(cookies)} 个 Cookie")

    # 方式2：从单独环境变量读取（覆盖 XHS_COOKIES 中的同名字段）
    env_map = {
        "XHS_A1": "a1",
        "XHS_WEB_SESSION": "web_session",
        "XHS_WEB_ID": "webId",
        "XHS_XSECAPPID": "xsecappid",
        "XHS_AB_REQUEST_ID": "abRequestId",
        "XHS_ACW_TC": "acw_tc",
    }
    env_loaded = 0
    for env_key, cookie_key in env_map.items():
        val = os.environ.get(env_key, "").strip()
        if val:
            cookies[cookie_key] = val
            env_loaded += 1
    if env_loaded > 0:
        logger.info(f"从单独环境变量加载 {env_loaded} 个 Cookie")

    # 从 cookies_xhs.txt 读取（补充环境变量中缺失的字段）
    cookie_file = ROOT / "cookies_xhs.txt"
    if cookie_file.exists():
        try:
            raw = cookie_file.read_text(encoding="utf-8").strip()
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # 映射到标准 cookie 名
                if key == "a1" or key == "A1" or key == "XHS_A1":
                    if "a1" not in cookies:
                        cookies["a1"] = value
                elif key == "web_session" or key == "XHS_WEB_SESSION":
                    if "web_session" not in cookies:
                        cookies["web_session"] = value
                elif key == "webId" or key == "XHS_WEB_ID":
                    if "webId" not in cookies:
                        cookies["webId"] = value
                else:
                    # 保留原始名
                    if key not in cookies:
                        cookies[key] = value
            logger.info(f"从 cookies_xhs.txt 加载 Cookie，共 {len(cookies)} 个字段")
        except Exception as exc:
            logger.warning(f"读取 cookies_xhs.txt 失败：{exc}")

    if not cookies.get("a1"):
        logger.warning("缺少 a1 Cookie，签名可能无效")
    if not cookies.get("web_session"):
        logger.warning("缺少 web_session Cookie，请求可能被拒绝")

    _cookies_cache = cookies
    return cookies


def _build_cookie_header(cookies: dict[str, str]) -> str:
    """将 Cookie 字典拼接为 HTTP Cookie 头字符串。"""
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


# ============================================================
# HTTP 请求基础设施
# ============================================================

def _random_delay() -> None:
    """随机延迟 0.5~1.5 秒，防止频率限制。"""
    time.sleep(random.uniform(0.5, 1.5))


def _request(
    url: str,
    method: str = "GET",
    params: Optional[dict] = None,
    body: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: int = 15,
    retries: int = 2,
) -> dict[str, Any]:
    """发送 HTTP 请求，自动附加签名和 Cookie。

    Args:
        url: 完整 URL
        method: HTTP 方法
        params: GET 查询参数
        body: POST JSON body
        headers: 额外请求头（会合并到默认头）
        timeout: 超时秒数
        retries: 重试次数

    Returns:
        响应 JSON 字典

    Raises:
        RuntimeError: 请求失败或响应异常
    """
    cookies = load_xhs_cookies()
    req_headers = dict(XHS_HEADERS)
    if headers:
        req_headers.update(headers)

    # Cookie 头
    req_headers["Cookie"] = _build_cookie_header(cookies)

    # 构造完整 URL
    if params and method.upper() == "GET":
        query = urlencode(sorted(params.items()))
        full_url = f"{url}?{query}" if query else url
    else:
        full_url = url

    # 解析 URI 路径（用于签名）
    parsed = urlparse(full_url)
    # window._webmsxyw() 对于 GET 请求需要包含查询参数的完整路径
    if parsed.query:
        sign_uri = f"{parsed.path}?{parsed.query}"
    else:
        sign_uri = parsed.path

    # 生成 X-s 签名
    # 优先使用 Playwright 的 window._webmsxyw() 签名（v55，有效）
    # 如果签名超时（可能是 worker 线程忙），等待后重试一次
    # 仅当重试仍失败时才回退到旧签名（可能无效）
    a1 = cookies.get("a1", "")
    post_body = body if (method.upper() == "POST" and body) else None
    signed = False
    for sign_attempt in range(2):
        try:
            signs = xhs_login._sign(sign_uri, post_body, a1=a1)
            req_headers["X-s"] = signs["x-s"]
            req_headers["X-t"] = signs["x-t"]
            signed = True
            break
        except Exception as exc:
            if sign_attempt == 0:
                logger.warning(f"Playwright 签名首次失败，1 秒后重试: {exc}")
                time.sleep(1)
            else:
                logger.warning(f"Playwright 签名重试仍失败，回退到旧签名: {exc}")

    if not signed:
        xs = xhs_sign.sign(parsed.path, a1, params=body if post_body else params, method=method)
        req_headers["X-s"] = xs
        req_headers["X-t"] = str(int(time.time() * 1000))

    # POST body
    post_data = None
    if method.upper() == "POST" and body:
        post_data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    # 发送请求（含重试）
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                full_url,
                data=post_data,
                headers=req_headers,
                method=method,
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                resp_body = resp.read().decode("utf-8", errors="replace")
                if status != 200:
                    logger.warning(f"HTTP {status} url={full_url} body={resp_body[:300]}")
                    raise RuntimeError(f"HTTP {status}: {resp_body[:200]}")
                try:
                    data = json.loads(resp_body)
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"响应非 JSON: {resp_body[:200]}") from e
                return data

        except urllib.error.HTTPError as e:
            last_exc = e
            resp_body = ""
            try:
                resp_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            logger.warning(
                f"HTTP 错误 {e.code} url={full_url} "
                f"attempt={attempt + 1}/{retries + 1} body={resp_body[:200]}"
            )
            if e.code == 403:
                logger.error(
                    "收到 403 Forbidden，可能是 Cookie 过期或签名无效。"
                    "请检查 XHS_A1 / XHS_WEB_SESSION 环境变量或 cookies_xhs.txt，"
                    "也可设置 XHS_COOKIES 环境变量传入完整 Cookie 字符串。"
                )
                raise RuntimeError("403 Forbidden：Cookie 过期或签名无效") from e
            if attempt < retries:
                _random_delay()
                continue
            raise RuntimeError(f"HTTP {e.code}: {resp_body[:200]}") from e

        except urllib.error.URLError as e:
            last_exc = e
            logger.warning(
                f"网络错误 url={full_url} attempt={attempt + 1}/{retries + 1}: {e}"
            )
            if attempt < retries:
                _random_delay()
                continue
            raise RuntimeError(f"网络请求失败: {e}") from e

        except RuntimeError:
            raise

        except Exception as e:
            last_exc = e
            logger.warning(f"请求异常 url={full_url}: {e}")
            if attempt < retries:
                _random_delay()
                continue
            raise RuntimeError(f"请求失败: {e}") from e

    # 不应到达此处
    raise RuntimeError(f"请求失败（重试耗尽）: {last_exc}")


# ============================================================
# 链接解析
# ============================================================

def resolve_note_id(raw_url: str) -> tuple[str, str, str]:
    """解析小红书链接，提取 note_id 和 xsec_token。

    支持格式：
        - xhslink.com/xxx 短链（302 重定向）
        - www.xiaohongshu.com/explore/{note_id}
        - www.xiaohongshu.com/discovery/item/{note_id}（旧版）
        - URL 中 ?xsec_token=xxx 参数

    Args:
        raw_url: 小红书链接

    Returns:
        (final_url, note_id, xsec_token)

    Raises:
        RuntimeError: 无法解析 note_id
    """
    url = raw_url.strip()

    # 短链重定向（xhslink.com/o/xxx 或 xhslink.com/xxx）
    if "xhslink.com" in url or "xhs.cn" in url:
        try:
            # 用 GET 请求（HEAD 可能被拒绝），添加 User-Agent
            req = urllib.request.Request(
                url,
                method="GET",
                headers={
                    "User-Agent": _UA,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
            )
            # 自定义 opener 跟随重定向
            opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
            resp = opener.open(req, timeout=15)
            final_url = resp.url
            # 如果重定向后的 URL 仍然不含 note_id，尝试从 HTML 中提取
            if not re.search(r"/(?:explore|discovery/item|note)/[a-f0-9]{20,}", final_url):
                try:
                    body = resp.read().decode("utf-8", errors="replace")
                    # 从 HTML 中的 window.__INITIAL_STATE__ 或 meta 标签提取
                    m = re.search(r'"noteId"\s*:\s*"([a-f0-9]{20,})"', body)
                    if m:
                        final_url = f"https://www.xiaohongshu.com/explore/{m.group(1)}"
                        logger.info(f"从 HTML 提取 note_id: {m.group(1)}")
                    # 也尝试从 og:url meta 标签提取
                    if "xiaohongshu.com" not in final_url:
                        m2 = re.search(r'og:url"\s*content="([^"]+)"', body)
                        if m2:
                            final_url = m2.group(1)
                except Exception:
                    pass
            url = final_url
            logger.info(f"短链重定向: {raw_url} -> {url}")
        except Exception as e:
            logger.warning(f"短链解析失败，尝试直接解析: {e}")

    # 提取 xsec_token
    xsec_token = ""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "xsec_token" in qs:
        xsec_token = qs["xsec_token"][0]
    elif "xsec_token" in url:
        # 兼容 URL 片段中的 token
        match = re.search(r"xsec_token=([a-zA-Z0-9_-]+)", url)
        if match:
            xsec_token = match.group(1)

    # 提取 note_id
    note_id = ""

    # /explore/{note_id}
    match = re.search(r"/explore/([a-f0-9]+)", url)
    if match:
        note_id = match.group(1)

    # /discovery/item/{note_id}
    if not note_id:
        match = re.search(r"/discovery/item/([a-f0-9]+)", url)
        if match:
            note_id = match.group(1)

    # /note/{note_id}
    if not note_id:
        match = re.search(r"/note/([a-f0-9]+)", url)
        if match:
            note_id = match.group(1)

    # /search_result/...keyword=...&id=xxx
    if not note_id:
        match = re.search(r"[?&]id=([a-f0-9]+)", url)
        if match:
            note_id = match.group(1)

    if not note_id:
        raise RuntimeError(f"无法从 URL 解析 note_id: {url}")

    logger.info(f"解析结果: note_id={note_id} xsec_token={'有' if xsec_token else '无'}")
    return url, note_id, xsec_token


# ============================================================
# 笔记详情
# ============================================================

def fetch_note_info(
    note_id: str,
    xsec_token: str = "",
) -> dict[str, Any]:
    """获取笔记详情。

    通过访问笔记 HTML 页面，从 window.__INITIAL_STATE__ 提取数据。
    这种方式不需要 API 签名，更稳定。

    Args:
        note_id: 笔记 ID
        xsec_token: 安全令牌（可为空）

    Returns:
        笔记信息字典，包含 title, desc, type, user, interactInfo, time,
        ipLocation, imageList, video 等字段
    """
    import re
    from urllib.parse import quote

    # 构建 HTML 页面 URL
    xsec_source = "pc_feed"
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    if xsec_token:
        url += f"?xsec_token={quote(xsec_token)}&xsec_source={xsec_source}"

    # 加载 Cookie
    cookies = load_xhs_cookies()
    cookie_str = _build_cookie_header(cookies)

    # HTML 页面请求头（不用 XHS_HEADERS，避免 Content-Type: json 导致 404）
    headers = {
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cookie": cookie_str,
        "Referer": "https://www.xiaohongshu.com/",
    }

    logger.info(f"fetch_note_info 开始：note_id={note_id} xsec_token={'有' if xsec_token else '无'}")
    logger.info(f"fetch_note_info HTML URL: {url}")
    logger.info(f"fetch_note_info Cookie 字段: {list(cookies.keys())}")

    req = urllib.request.Request(url, headers=headers, method="GET")
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8")
            logger.info(f"fetch_note_info HTML 获取成功：{len(html)} 字节")
            break
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            logger.warning(f"获取笔记 HTML 失败 HTTP {e.code} attempt={attempt}/3 body={body_text[:100]}")
            if attempt == 3:
                raise RuntimeError(f"获取笔记详情失败 HTTP {e.code}: {body_text[:200]}") from e
            _random_delay()

    _random_delay()

    # 从 HTML 中提取 window.__INITIAL_STATE__
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*</script>", html)
    if not match:
        logger.error(f"未找到 __INITIAL_STATE__：note_id={note_id} HTML长度={len(html)}")
        raise RuntimeError(f"未找到 __INITIAL_STATE__: note_id={note_id}")

    state_str = match.group(1).replace("undefined", '""')
    state = json.loads(state_str)
    logger.info(f"fetch_note_info __INITIAL_STATE__ 解析成功")

    # 提取笔记数据
    note_map = state.get("note", {}).get("noteDetailMap", {})
    if note_id not in note_map:
        # 尝试取第一个
        if note_map:
            note_id_key = list(note_map.keys())[0]
        else:
            raise RuntimeError(f"笔记详情为空: note_id={note_id}")
    else:
        note_id_key = note_id

    note_data = note_map[note_id_key].get("note", {})

    # 提取用户信息
    user_info = note_data.get("user", {})
    user = {
        "userId": user_info.get("userId", user_info.get("user_id", "")),
        "nickname": user_info.get("nickname", ""),
        "avatar": user_info.get("avatar", ""),
    }

    # 提取交互信息（HTML 格式用驼峰命名）
    interact = note_data.get("interactInfo", note_data.get("interact_info", {}))
    interact_info = {
        "liked": str(interact.get("liked", False)),
        "likes": interact.get("likedCount", interact.get("liked_count", "0")),
        "collected": str(interact.get("collected", False)),
        "collectedCount": interact.get("collectedCount", interact.get("collected_count", "0")),
        "commentCount": interact.get("commentCount", interact.get("comment_count", "0")),
        "shareCount": interact.get("shareCount", interact.get("share_count", "0")),
    }

    # 提取图片列表
    image_list = []
    for img in note_data.get("imageList", note_data.get("image_list", [])):
        info_list = img.get("infoList", img.get("info_list", [{}]))
        url_item = info_list[0] if info_list else {}
        image_list.append({
            "url": url_item.get("url", ""),
            "width": img.get("width", 0),
            "height": img.get("height", 0),
        })

    # 提取视频信息
    video_info = note_data.get("video", {})
    video = {}
    if video_info:
        video = {
            "url": video_info.get("url", ""),
            "duration": video_info.get("duration", 0),
            "width": video_info.get("width", 0),
            "height": video_info.get("height", 0),
        }

    # 笔记类型
    note_type = note_data.get("type", "normal")
    type_str = "video" if note_type == "video" else "image"

    result = {
        "noteId": note_id,
        "title": note_data.get("title", ""),
        "desc": note_data.get("desc", ""),
        "type": type_str,
        "user": user,
        "interactInfo": interact_info,
        "time": note_data.get("time", 0),
        "ipLocation": note_data.get("ipLocation", note_data.get("ip_location", "")),
        "imageList": image_list,
        "video": video,
        "tagList": note_data.get("tagList", note_data.get("tag_list", [])),
        "xsecToken": note_data.get("xsecToken", note_data.get("xsec_token", xsec_token)),
    }

    logger.info(f"获取笔记详情成功（HTML）: note_id={note_id} title={result['title'][:30]}")
    return result


# ============================================================
# 评论抓取
# ============================================================

def fetch_comments(
    note_id: str,
    xsec_token: str = "",
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    """获取笔记评论（含子评论）。

    策略：
    1. 优先用 Playwright DOM 提取初始评论（避免 461 验证码）
    2. 然后用 API 翻页获取更多评论（通过浏览器 fetch 自动签名，避免签名超时）
    3. 合并去重

    Args:
        note_id: 笔记 ID
        xsec_token: 安全令牌
        max_pages: 最大翻页数

    Returns:
        标准格式评论列表:
        [{user, mid, text, likes, time, rpid, ip_location}, ...]
    """
    logger.info(f"fetch_comments 开始：note_id={note_id} xsec_token={'有' if xsec_token else '无'} max_pages={max_pages}")

    all_comments: list[dict[str, Any]] = []
    seen_mids: set[str] = set()

    def _add_comment(c: dict[str, Any]) -> None:
        mid = c.get("mid", "")
        if mid and mid in seen_mids:
            return
        if mid:
            seen_mids.add(mid)
        all_comments.append(c)

    # ============================================================
    # 阶段1：Playwright DOM 提取初始评论
    # ============================================================
    dom_ok = False
    if xhs_login.is_available():
        try:
            from urllib.parse import quote
            note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
            if xsec_token:
                note_url += f"?xsec_token={quote(xsec_token)}&xsec_source=pc_feed"

            logger.info(f"fetch_comments 使用 Playwright DOM 提取：{note_url}")
            result = xhs_login.extract_comments_from_page(note_url)
            logger.info(f"fetch_comments Playwright 结果: domCount={result.get('domCount', 0)} domComments={len(result.get('domComments', []))} stateComments={len(result.get('stateComments', []))}")

            # 优先用 __INITIAL_STATE__ 中的评论（数据更完整）
            state_comments = result.get("stateComments", [])
            if state_comments:
                for c in state_comments:
                    _add_comment(to_standard_comments(c))
                    for sc in c.get("sub_comments", []):
                        _add_comment(to_standard_comments(sc))
                logger.info(f"从 __INITIAL_STATE__ 提取评论: {len(all_comments)} 条")
                dom_ok = True

            # 回退到 DOM 评论
            if not all_comments:
                dom_comments = result.get("domComments", [])
                for i, c in enumerate(dom_comments):
                    _add_comment({
                        "user": {"nickname": c.get("user", ""), "user_id": ""},
                        "mid": f"dom_{i}",
                        "text": c.get("content", ""),
                        "likes": c.get("likes", "0"),
                        "time": 0,
                        "rpid": "",
                        "ip_location": "",
                    })
                if all_comments:
                    logger.info(f"从 DOM 提取评论: {len(all_comments)} 条")
                    dom_ok = True

            if not all_comments:
                logger.warning("DOM 和 State 评论均为空")
        except Exception as exc:
            logger.warning(f"Playwright 提取评论失败: {exc}")

    # ============================================================
    # 阶段2：API 翻页获取更多评论
    # ============================================================
    # 如果 DOM 提取成功但评论较少，或者 DOM 提取失败，尝试 API 翻页
    should_try_api = (not dom_ok) or (len(all_comments) < 20)
    if should_try_api:
        logger.info(f"fetch_comments 尝试 API 翻页获取更多评论（当前 {len(all_comments)} 条）")
        cursor = ""
        try:
            for page_num in range(max_pages):
                params: dict[str, Any] = {
                    "note_id": note_id,
                    "cursor": cursor,
                    "image_formats": "jpg,webp,avif",
                    "top_comment_id": "",
                    "xsec_token": xsec_token,
                }
                params = {k: v for k, v in params.items() if v}

                api_url = "https://edith.xiaohongshu.com/api/sns/web/v2/comment/page"
                query = urlencode(sorted(params.items()))
                full_api_url = f"{api_url}?{query}" if query else api_url

                # 优先用浏览器 fetch（自动签名+Cookie，避免签名队列超时）
                data = None
                if xhs_login.is_available():
                    try:
                        fetch_result = xhs_login.fetch_via_browser(full_api_url, method="GET")
                        status = fetch_result.get("status")
                        if status == 200:
                            try:
                                data = json.loads(fetch_result["body"])
                            except json.JSONDecodeError:
                                logger.warning(f"浏览器 fetch 返回非 JSON: {fetch_result.get('body', '')[:200]}")
                        elif status == 461:
                            # 461 = 小红书验证码，签名可能无效或被风控
                            # 不重试浏览器 fetch，直接用 _request（带 Playwright 签名）
                            logger.warning(f"浏览器 fetch 返回 461（验证码），回退到 _request")
                        else:
                            logger.warning(f"浏览器 fetch 返回 {status}: {fetch_result.get('body', '')[:200]}")
                    except Exception as fetch_exc:
                        logger.warning(f"浏览器 fetch 失败，回退到 _request: {fetch_exc}")

                # 回退到 _request（带 Playwright 签名 + 重试）
                if data is None:
                    try:
                        data = _request(api_url, method="GET", params=params)
                    except Exception as req_exc:
                        logger.warning(f"_request 也失败: {req_exc}")
                        break

                _random_delay()

                if data.get("code") != 0 or "data" not in data:
                    error_msg = data.get("msg", "未知错误")
                    logger.warning(f"API 获取评论失败 page={page_num}: {error_msg}")
                    break

                comment_data = data["data"]
                comments = comment_data.get("comments", [])
                cursor = comment_data.get("cursor", "")
                has_more = comment_data.get("has_more", False)

                before = len(all_comments)
                for c in comments:
                    _add_comment(to_standard_comments(c))
                    sub_comments = c.get("sub_comments", [])
                    for sc in sub_comments:
                        _add_comment(to_standard_comments(sc))

                added = len(all_comments) - before
                logger.info(f"API 评论第 {page_num + 1} 页: 新增 {added} 条, 累计 {len(all_comments)} 条")

                if not has_more or not cursor:
                    break
        except Exception as api_exc:
            logger.warning(f"API 获取评论失败: {api_exc}")
            if not all_comments:
                logger.warning("DOM 和 API 均未获取到评论，返回空列表")
                return []

    logger.info(f"评论抓取完成: note_id={note_id} 共 {len(all_comments)} 条")
    return all_comments


# ============================================================
# 搜索笔记
# ============================================================

def search_notes(
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    sort: str = "general",
) -> dict[str, Any]:
    """搜索小红书笔记。

    API: POST /api/sns/web/v1/search/notes

    Args:
        keyword: 搜索关键词
        page: 页码（从 1 开始）
        page_size: 每页数量
        sort: 排序方式（general/popularity/latest）

    Returns:
        搜索结果字典:
        {keyword, page, results: [{id, title, user, interactInfo, xsecToken, type}], ...}
    """
    url = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"
    body = {
        "keyword": keyword,
        "page": page,
        "page_size": page_size,
        "sort": sort,
        "note_type": 0,
    }

    data = _request(url, method="POST", body=body)
    _random_delay()

    if data.get("code") != 0 or "data" not in data:
        error_msg = data.get("msg", "未知错误")
        logger.error(f"搜索笔记失败: {error_msg}")
        raise RuntimeError(f"搜索笔记失败: {error_msg}")

    items = data["data"].get("items", [])
    results = []
    for item in items:
        note = item.get("note_card", {})
        if not note:
            continue

        user_info = note.get("user", {})
        interact = note.get("interact_info", {})

        note_type = note.get("type", "normal")
        type_str = "video" if note_type == "video" else "image"

        results.append({
            "id": note.get("note_id", ""),
            "title": note.get("title", ""),
            "desc": note.get("desc", "")[:100],
            "type": type_str,
            "user": {
                "userId": user_info.get("user_id", ""),
                "nickname": user_info.get("nickname", ""),
                "avatar": user_info.get("avatar", ""),
            },
            "interactInfo": {
                "likes": interact.get("liked_count", "0"),
                "commentCount": interact.get("comment_count", "0"),
            },
            "xsecToken": note.get("xsec_token", ""),
            "time": note.get("time", 0),
        })

    result = {
        "keyword": keyword,
        "page": page,
        "total": data["data"].get("total", 0),
        "results": results,
    }

    logger.info(f"搜索完成: keyword={keyword} page={page} results={len(results)}")
    return result


# ============================================================
# 评论格式转换
# ============================================================

def to_standard_comments(raw: dict[str, Any]) -> dict[str, Any]:
    """将小红书评论转换为标准格式。

    小红书原始格式 -> 标准格式:
        user.nickname    -> user
        comment_content  -> text
        like_count       -> likes (str -> int)
        create_time      -> time (unix ts -> 格式化字符串)
        id               -> mid
        target_comment_id -> rpid
        ip_location      -> ip_location

    Args:
        raw: 小红书 API 返回的单条评论字典

    Returns:
        标准格式评论字典
    """
    user_info = raw.get("user", {})
    nickname = user_info.get("nickname", "匿名用户")
    user_id = user_info.get("user_id", "")

    # likes 是字符串，需要转 int
    like_count = raw.get("like_count", "0")
    try:
        likes = int(like_count)
    except (ValueError, TypeError):
        likes = 0

    # create_time 是 Unix 时间戳（秒），格式化为可读字符串
    create_time = raw.get("create_time", 0)
    try:
        ts = int(create_time)
        if ts > 0:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = ""
    except (ValueError, TypeError, OSError):
        time_str = str(create_time)

    # IP 归属地
    ip_location = raw.get("ip_location", "")

    return {
        "user": nickname,
        "userId": user_id,
        "mid": raw.get("id", ""),
        "text": raw.get("content", ""),
        "likes": likes,
        "time": time_str,
        "rpid": raw.get("target_comment_id", ""),
        "ip_location": ip_location,
        "sub_comment_count": raw.get("sub_comment_count", 0),
    }


# ============================================================
# 便捷入口
# ============================================================

def fetch_note_comments(
    url_or_id: str,
    max_pages: int = 5,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """一站式获取笔记信息和评论。

    Args:
        url_or_id: 小红书链接或 note_id
        max_pages: 最大翻页数

    Returns:
        (note_info, comments) 元组
    """
    # 判断是 URL 还是 note_id
    if url_or_id.startswith("http"):
        _, note_id, xsec_token = resolve_note_id(url_or_id)
    else:
        note_id = url_or_id.strip()
        xsec_token = ""

    note_info = fetch_note_info(note_id, xsec_token)

    # 优先使用笔记返回的 xsec_token
    token = xsec_token or note_info.get("xsecToken", "")
    comments = fetch_comments(note_id, token, max_pages)

    return note_info, comments


# ============================================================
# 扫码登录
# ============================================================

# 登录会话期间的 Cookie 缓存（init_session 获取，poll 时复用）
_login_cookies: dict[str, str] = {}


def get_a1_and_web_id() -> tuple[str, str]:
    """本地生成 a1 和 webId（无需访问小红书首页）。

    基于 ReaJason/xhs 的生成算法。

    Returns:
        (a1, webId) 元组
    """
    import binascii
    import string

    d = hex(int(time.time() * 1000))[2:] + "".join(
        random.choice(string.ascii_letters + string.digits) for _ in range(30)
    ) + "5" + "0" + "000"
    g = (d + str(binascii.crc32(str(d).encode("utf-8"))))[:52]
    return g, hashlib.md5(g.encode("utf-8")).hexdigest()


def init_session() -> dict[str, str]:
    """访问小红书首页获取初始 Cookie（特别是 a1 设备指纹）。

    如果首页未返回 a1，则本地生成。

    Returns:
        Cookie 字典，至少包含 a1
    """
    global _login_cookies

    import http.cookiejar

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    req = urllib.request.Request(
        "https://www.xiaohongshu.com/explore",
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    try:
        resp = opener.open(req, timeout=15)
        resp.read()
    except Exception as e:
        logger.warning(f"初始化小红书会话失败: {e}")

    cookies = {c.name: c.value for c in cookie_jar}

    # 如果首页未返回 a1，本地生成
    if not cookies.get("a1"):
        a1, web_id = get_a1_and_web_id()
        cookies["a1"] = a1
        cookies["webId"] = web_id
        logger.info("首页未返回 a1，已本地生成")

    # 缓存登录会话 Cookie
    _login_cookies = cookies
    logger.info(
        f"小红书会话初始化，获取到 {len(cookies)} 个 Cookie，a1={'有' if 'a1' in cookies else '无'}"
    )
    return cookies


def create_qrcode(cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """调用小红书 API 生成登录二维码。

    Args:
        cookies: Cookie 字典（至少包含 a1），为 None 时使用 _login_cookies

    Returns:
        {"url": str, "qr_id": str, "code": str}
    """
    from analysis.xhs_sign import sign_legacy

    if cookies is None:
        cookies = _login_cookies or {}
    a1 = cookies.get("a1", "")

    uri = "/api/sns/web/v1/login/qrcode/create"
    api_url = "https://edith.xiaohongshu.com" + uri
    body = {"qr_type": 1}
    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    # 生成 Legacy 签名（x-s / x-t / x-s-common）
    signs = sign_legacy(uri, data=body, a1=a1)

    headers = dict(XHS_HEADERS)
    headers["X-s"] = signs["x-s"]
    headers["X-t"] = signs["x-t"]
    headers["X-s-common"] = signs["x-s-common"]
    # 关键：必须携带 Cookie 头（至少包含 a1）
    headers["Cookie"] = _build_cookie_header(cookies)

    req = urllib.request.Request(api_url, data=body_json, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"创建二维码失败 HTTP {e.code}: {body_text[:200]}") from e

    if result.get("code") != 0 or not result.get("success"):
        raise RuntimeError(f"创建二维码失败: {result.get('msg', '未知错误')}")

    data = result["data"]
    logger.info(f"小红书二维码已生成: qr_id={data['qr_id']}")
    return {
        "url": data["url"],
        "qr_id": data["qr_id"],
        "code": data["code"],
    }


def poll_qrcode(
    qr_id: str,
    code: str,
    cookies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """轮询小红书扫码登录状态。

    Args:
        qr_id: 二维码 ID
        code: 二维码 code
        cookies: Cookie 字典，为 None 时使用 _login_cookies

    Returns:
        {
            "code_status": int,  # 0=未扫码, 1=已扫码, 2=成功, 3=失效
            "login_info": dict,  # 仅成功时有
            "cookies": dict,     # 仅成功时有，从 Set-Cookie 提取
        }
    """
    from analysis.xhs_sign import sign_legacy

    if cookies is None:
        cookies = _login_cookies or {}
    a1 = cookies.get("a1", "")

    params = {"qr_id": qr_id, "code": code}
    uri = "/api/sns/web/v1/login/qrcode/status"
    query_str = urllib.parse.urlencode(params)
    full_uri = f"{uri}?{query_str}"
    api_url = "https://edith.xiaohongshu.com" + full_uri

    # 生成 Legacy 签名
    signs = sign_legacy(uri, data=None, a1=a1)

    headers = dict(XHS_HEADERS)
    headers["X-s"] = signs["x-s"]
    headers["X-t"] = signs["x-t"]
    headers["X-s-common"] = signs["x-s-common"]
    headers["Cookie"] = _build_cookie_header(cookies)

    req = urllib.request.Request(api_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            # 提取 Set-Cookie 中的登录凭证
            resp_cookies = {}
            for header in resp.headers.get_all("Set-Cookie") or []:
                parts = header.split(";")[0].strip().split("=", 1)
                if len(parts) == 2:
                    resp_cookies[parts[0].strip()] = parts[1].strip()

            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"轮询扫码状态失败 HTTP {e.code}: {body_text[:200]}") from e

    if result.get("code") != 0 or not result.get("success"):
        raise RuntimeError(f"轮询失败: {result.get('msg', '未知错误')}")

    data = result["data"]
    code_status = data.get("code_status", 0)

    ret = {"code_status": code_status, "login_info": {}, "cookies": {}}
    if code_status == 2:
        ret["login_info"] = data.get("login_info", {})
        # 合并已有 cookies 和响应中的新 cookies
        merged = dict(cookies)
        merged.update(resp_cookies)
        ret["cookies"] = merged
        logger.info(f"小红书扫码登录成功！获取到 {len(merged)} 个 Cookie")

    return ret


def save_qrcode_cookies(cookies: dict[str, str]) -> None:
    """将扫码登录获取的 Cookie 保存到 cookies_xhs.txt"""
    cookie_file = ROOT / "cookies_xhs.txt"
    lines = []
    for key in ("a1", "web_session", "webId"):
        if cookies.get(key):
            lines.append(f"{key}={cookies[key]}")
    cookie_file.write_text("\n".join(lines), encoding="utf-8")
    # 清除缓存
    global _cookies_cache
    _cookies_cache = None
    logger.info(f"小红书 Cookie 已保存到 {cookie_file}")
