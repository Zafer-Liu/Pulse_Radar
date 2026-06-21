"""小红书扫码登录模块 -- API 方式（像 B站一样）

工作流程（和 B站完全一样）：
    1. create_qrcode()  调用小红书 API 生成二维码 → 返回 {url, qr_id, code}
    2. 前端用 qrcode.js 渲染 url 为二维码图片
    3. poll_qrcode()    轮询 API 状态 → 返回 {code_status, cookies}

签名方案：
    小红书 API 需要 X-s 签名（v55），只能通过 window._webmsxyw() JS 函数生成。
    使用 Playwright 无头浏览器加载小红书页面，调用该函数进行签名。
    Playwright 仅用于签名（不用于截图/显示），二维码通过 API 获取。

线程安全：
    Playwright sync API 不是线程安全的。所有 Playwright 操作都在一个
    专用后台线程中执行，HTTP 线程通过队列与它通信。
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

logger = logging.getLogger("xhs_login")

# ============================================================
# 常量
# ============================================================

_API_HOST = "https://edith.xiaohongshu.com"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# ============================================================
# 签名服务 -- 后台线程运行 Playwright
# ============================================================

_lock = threading.Lock()
_worker_thread: threading.Thread | None = None
_cmd_queue: queue.Queue = queue.Queue()
_result_queue: queue.Queue = queue.Queue()
_a1_value: str = ""  # 从浏览器获取的 a1 cookie


def _is_playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _load_saved_cookies() -> list[dict]:
    """从 cookies_xhs.txt 读取已保存的 cookie，返回 Playwright cookie 格式。"""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    cookie_file = root / "cookies_xhs.txt"
    if not cookie_file.exists():
        return []

    cookies = []
    try:
        raw = cookie_file.read_text(encoding="utf-8").strip()
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            cookies.append({
                "name": key.strip(),
                "value": value.strip(),
                "domain": ".xiaohongshu.com",
                "path": "/",
            })
        logger.info(f"签名服务：从 cookies_xhs.txt 加载 {len(cookies)} 个 Cookie")
    except Exception as e:
        logger.warning(f"签名服务：读取 cookies_xhs.txt 失败: {e}")
    return cookies


def _worker_loop():
    """后台工作线程：加载小红书页面，处理签名请求。"""
    global _a1_value

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("playwright 未安装，签名服务不可用")
        return

    pw = None
    browser = None
    page = None

    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 720},
        )
        page = context.new_page()

        logger.info("签名服务：正在加载小红书页面...")
        page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # 如果用户已登录（cookies_xhs.txt 存在），注入保存的 cookie
        # 不重新加载页面，避免触发验证码
        # 这样签名用的 a1 和请求用的 a1 一致，避免 406
        saved_cookies = _load_saved_cookies()
        if saved_cookies:
            context.add_cookies(saved_cookies)
            logger.info("签名服务：已注入用户 Cookie（不重新加载页面）")

        # 获取 a1 cookie（优先用用户保存的）
        cookies = context.cookies()
        for c in cookies:
            if c["name"] == "a1":
                _a1_value = c["value"]
                logger.info(f"签名服务：获取到 a1 = {_a1_value[:20]}...")
                break

        if not _a1_value:
            logger.warning("签名服务：未获取到 a1 cookie，签名可能失败")

        logger.info("签名服务就绪")

        # 主循环：处理签名请求
        while True:
            try:
                cmd = _cmd_queue.get(timeout=1)
            except queue.Empty:
                continue

            if cmd is None:
                break

            cmd_type = cmd[0]

            if cmd_type == "sign":
                uri = cmd[1]
                data = cmd[2]
                try:
                    # 调用 window._webmsxyw(url, data) 获取签名
                    # 浏览器 cookie store 中已有用户保存的 a1（通过 context.add_cookies 注入）
                    encrypt_params = page.evaluate(
                        "([url, data]) => window._webmsxyw(url, data)",
                        [uri, data],
                    )
                    result = {
                        "x-s": encrypt_params["X-s"],
                        "x-t": str(encrypt_params["X-t"]),
                    }
                    _result_queue.put({"ok": True, "signs": result})
                except Exception as e:
                    logger.warning(f"签名失败: {e}")
                    _result_queue.put({"ok": False, "error": str(e)})

            elif cmd_type == "get_a1":
                _result_queue.put({"ok": True, "a1": _a1_value})

            elif cmd_type == "get_browser_cookies":
                # 获取 Playwright 浏览器中的所有 Cookie（用于扫码登录后保存完整 cookie）
                try:
                    all_cookies = context.cookies()
                    cookie_dict = {}
                    for c in all_cookies:
                        name = c.get("name", "")
                        value = c.get("value", "")
                        if name and value:
                            cookie_dict[name] = value
                    logger.info(f"获取浏览器 Cookie: {len(cookie_dict)} 个字段 ({list(cookie_dict.keys())})")
                    _result_queue.put({"ok": True, "cookies": cookie_dict})
                except Exception as e:
                    logger.warning(f"获取浏览器 Cookie 失败: {e}")
                    _result_queue.put({"ok": False, "error": str(e)})

            elif cmd_type == "navigate_and_extract_comments":
                # 导航到笔记页面，等待评论加载，从 DOM 提取评论
                # 使用新标签页，避免干扰签名页面
                nav_url = cmd[1]
                comment_page = None
                try:
                    comment_page = context.new_page()
                    # networkidle 等待网络空闲，确保页面完全加载
                    comment_page.goto(nav_url, wait_until="networkidle", timeout=30000)
                    current_url = comment_page.url
                    logger.info(f"评论页面导航完成: {current_url}")

                    # 等待页面完全渲染
                    time.sleep(2)

                    # 滚动到页面底部，触发评论加载
                    try:
                        comment_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    except Exception:
                        pass
                    time.sleep(3)

                    # 再滚动一次确保评论加载
                    try:
                        comment_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    except Exception:
                        pass
                    time.sleep(5)

                    # 从 DOM 中提取评论（带重试，防止执行上下文被导航销毁）
                    js_extract = """
                    () => {
                        const comments = [];
                        // 小红书评论选择器 - 多种可能的选择器
                        const selectors = [
                            '.comment-item',
                            '.note-comment .comment',
                            '[class*="CommentItem"]',
                            '.comments-container .comment',
                            '.parent-comment',
                            '[class*="comment-item"]',
                            '[class*="comment"]',
                        ];
                        let items = [];
                        for (const sel of selectors) {
                            items = document.querySelectorAll(sel);
                            if (items.length > 0) break;
                        }

                        items.forEach(item => {
                            const nameEl = item.querySelector('.name, .user-name, .author, [class*="name"], .user-nickname');
                            const contentEl = item.querySelector('.content, .note-text, .desc, [class*="content"], .comment-content');
                            const likeEl = item.querySelector('.like-wrapper .count, .like-count, [class*="like"] [class*="count"]');
                            comments.push({
                                user: nameEl ? nameEl.textContent.trim() : '',
                                content: contentEl ? contentEl.textContent.trim() : '',
                                likes: likeEl ? likeEl.textContent.trim() : '0',
                            });
                        });

                        // 也从 __INITIAL_STATE__ 提取
                        let stateComments = [];
                        try {
                            const state = window.__INITIAL_STATE__;
                            if (state && state.note && state.note.noteDetailMap) {
                                const noteId = Object.keys(state.note.noteDetailMap)[0];
                                const noteData = state.note.noteDetailMap[noteId];
                                if (noteData && noteData.comments && noteData.comments.list) {
                                    stateComments = noteData.comments.list;
                                }
                            }
                        } catch(e) {}

                        // 获取页面标题和部分 HTML 用于调试
                        let debugInfo = {
                            title: document.title,
                            url: window.location.href,
                            bodyLength: document.body ? document.body.innerHTML.length : 0,
                        };

                        return { domComments: comments, stateComments: stateComments, domCount: items.length, debug: debugInfo };
                    }
                    """
                    result = None
                    for eval_attempt in range(3):
                        try:
                            result = comment_page.evaluate(js_extract)
                            break
                        except Exception as eval_e:
                            logger.warning(f"评论提取 evaluate 失败 attempt={eval_attempt+1}/3: {eval_e}")
                            if eval_attempt < 2:
                                time.sleep(3)
                                # 重新等待页面稳定
                                try:
                                    comment_page.wait_for_load_state("networkidle", timeout=10000)
                                except Exception:
                                    pass

                    if result is None:
                        result = {"domComments": [], "stateComments": [], "domCount": 0, "debug": {"error": "evaluate failed"}}

                    dbg = result.get("debug", {})
                    logger.info(
                        f"评论提取结果: domCount={result.get('domCount', 0)}, "
                        f"domComments={len(result.get('domComments', []))}, "
                        f"stateComments={len(result.get('stateComments', []))}, "
                        f"page={dbg.get('title', '?')}, bodyLen={dbg.get('bodyLength', 0)}"
                    )
                    _result_queue.put({"ok": True, "result": result})
                except Exception as e:
                    logger.warning(f"navigate_and_extract_comments 失败: {e}")
                    _result_queue.put({"ok": False, "error": str(e)})
                finally:
                    if comment_page:
                        try:
                            comment_page.close()
                        except Exception:
                            pass

            elif cmd_type == "navigate_and_fetch":
                # 先导航到页面，再在页面上下文中调用 API
                nav_url = cmd[1]
                api_url = cmd[2]
                try:
                    # 导航到笔记页面（建立会话）
                    page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(3)

                    # 在页面上下文中调用评论 API
                    js_code = """
                    async ([url]) => {
                        const resp = await fetch(url, {
                            method: 'GET',
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                            }
                        });
                        const text = await resp.text();
                        return { status: resp.status, body: text };
                    }
                    """
                    result = page.evaluate(js_code, [api_url])
                    _result_queue.put({"ok": True, "result": result})
                except Exception as e:
                    logger.warning(f"navigate_and_fetch 失败: {e}")
                    _result_queue.put({"ok": False, "error": str(e)})

            elif cmd_type == "fetch":
                # 在浏览器中直接调用 API（浏览器自动签名 + 发送 Cookie）
                fetch_url = cmd[1]
                fetch_method = cmd[2] if len(cmd) > 2 else "GET"
                fetch_body = cmd[3] if len(cmd) > 3 else None
                try:
                    js_code = """
                    async ([url, method, body]) => {
                        const opts = {
                            method: method,
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'Content-Type': 'application/json',
                            }
                        };
                        if (body && method === 'POST') {
                            opts.body = JSON.stringify(body);
                        }
                        const resp = await fetch(url, opts);
                        const text = await resp.text();
                        return { status: resp.status, body: text };
                    }
                    """
                    result = page.evaluate(js_code, [fetch_url, fetch_method, fetch_body])
                    _result_queue.put({"ok": True, "result": result})
                except Exception as e:
                    logger.warning(f"浏览器 fetch 失败: {e}")
                    _result_queue.put({"ok": False, "error": str(e)})

    except Exception as e:
        logger.exception(f"签名服务工作线程异常: {e}")
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
        logger.info("签名服务工作线程已退出")


def _ensure_worker():
    """确保签名服务工作线程正在运行。"""
    global _worker_thread

    if _worker_thread and _worker_thread.is_alive():
        return True

    if not _is_playwright_available():
        return False

    _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="xhs-sign-worker")
    _worker_thread.start()

    # 等待工作线程就绪（最多 40 秒）
    for _ in range(40):
        if _a1_value:
            return True
        time.sleep(1)

    return bool(_a1_value)


def _sign(uri: str, data: dict | None = None, a1: str = "") -> dict[str, str]:
    """调用签名服务获取 X-s 签名。

    Args:
        uri: API 路径（GET 请求可包含查询参数）
        data: POST 请求体（GET 请求为 None）
        a1: 用户保存的 a1 值。如果指定且与浏览器中的不同，
            会先修改 document.cookie 再签名，确保签名和 Cookie 一致。

    Returns:
        {"x-s": str, "x-t": str}
    """
    if not _ensure_worker():
        raise RuntimeError("签名服务不可用（Playwright 未安装或启动失败）")

    _cmd_queue.put(("sign", uri, data, a1))
    try:
        result = _result_queue.get(timeout=15)
        if result.get("ok"):
            return result["signs"]
        raise RuntimeError(f"签名失败: {result.get('error', '未知错误')}")
    except queue.Empty:
        raise RuntimeError("签名超时")


def get_a1() -> str:
    """获取当前签名服务的 a1 值。"""
    if not _ensure_worker():
        return ""
    _cmd_queue.put(("get_a1",))
    try:
        result = _result_queue.get(timeout=5)
        if result.get("ok"):
            return result.get("a1", "")
    except queue.Empty:
        pass
    return _a1_value


def get_browser_cookies() -> dict:
    """获取 Playwright 浏览器中的所有 Cookie。

    用于扫码登录成功后，从浏览器获取完整 Cookie（包括 webId、xsecappid 等
    API 响应中不包含的字段）。

    Returns:
        Cookie 字典，如 {"a1": "xxx", "web_session": "xxx", "webId": "xxx", ...}
        如果签名服务不可用则返回空字典。
    """
    if not _ensure_worker():
        return {}
    _cmd_queue.put(("get_browser_cookies",))
    try:
        result = _result_queue.get(timeout=10)
        if result.get("ok"):
            return result.get("cookies", {})
    except queue.Empty:
        pass
    return {}


def fetch_via_browser(url: str, method: str = "GET", body: dict | None = None) -> dict:
    """在 Playwright 浏览器中直接调用 API。

    浏览器会自动添加签名和 Cookie，避免 461 验证码。

    Args:
        url: 完整的 API URL
        method: HTTP 方法（GET/POST）
        body: POST 请求体（GET 请求为 None）

    Returns:
        {"status": int, "body": str}  其中 body 是响应文本
    """
    if not _ensure_worker():
        raise RuntimeError("签名服务不可用（Playwright 未安装或启动失败）")

    _cmd_queue.put(("fetch", url, method, body))
    try:
        result = _result_queue.get(timeout=30)
        if result.get("ok"):
            return result["result"]
        raise RuntimeError(f"浏览器 fetch 失败: {result.get('error', '未知错误')}")
    except queue.Empty:
        raise RuntimeError("浏览器 fetch 超时")


def navigate_and_fetch(nav_url: str, api_url: str) -> dict:
    """先导航到页面，再在页面上下文中调用 API。

    先用 page.goto 导航到笔记页面（建立会话），然后在页面中调用评论 API。
    这样浏览器会先"正常"访问页面，可能不会触发 461 验证码。

    Args:
        nav_url: 要导航的页面 URL（如笔记页面）
        api_url: 要调用的 API URL（如评论 API）

    Returns:
        {"status": int, "body": str}
    """
    if not _ensure_worker():
        raise RuntimeError("签名服务不可用（Playwright 未安装或启动失败）")

    _cmd_queue.put(("navigate_and_fetch", nav_url, api_url))
    try:
        result = _result_queue.get(timeout=60)
        if result.get("ok"):
            return result["result"]
        raise RuntimeError(f"navigate_and_fetch 失败: {result.get('error', '未知错误')}")
    except queue.Empty:
        raise RuntimeError("navigate_and_fetch 超时")


def extract_comments_from_page(note_url: str) -> dict:
    """导航到笔记页面，等待评论加载，从 DOM 和 __INITIAL_STATE__ 提取评论。

    Args:
        note_url: 笔记页面 URL

    Returns:
        {"domComments": list, "stateComments": list}
    """
    if not _ensure_worker():
        raise RuntimeError("签名服务不可用（Playwright 未安装或启动失败）")

    _cmd_queue.put(("navigate_and_extract_comments", note_url))
    try:
        result = _result_queue.get(timeout=60)
        if result.get("ok"):
            return result["result"]
        raise RuntimeError(f"提取评论失败: {result.get('error', '未知错误')}")
    except queue.Empty:
        raise RuntimeError("提取评论超时")


def is_available() -> bool:
    """检查扫码登录是否可用（Playwright 是否安装）。"""
    return _is_playwright_available()


# ============================================================
# API 调用 -- 和 B站一样的流程
# ============================================================

def _build_headers(signs: dict[str, str], a1: str) -> dict[str, str]:
    """构建请求头。"""
    headers = {
        "User-Agent": _UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://www.xiaohongshu.com",
        "Referer": "https://www.xiaohongshu.com/",
        "X-s": signs["x-s"],
        "X-t": signs["x-t"],
        "Cookie": f"a1={a1}; webId={a1[:32]}; xsecappid=xhs-pc-web",
    }
    return headers


def create_qrcode() -> dict:
    """调用小红书 API 生成登录二维码（和 B站一样的流程）。

    Returns:
        {"url": str, "qr_id": str, "code": str}
    """
    a1 = get_a1()
    if not a1:
        raise RuntimeError("无法获取 a1，签名服务未就绪")

    uri = "/api/sns/web/v1/login/qrcode/create"
    body = {"qr_type": 1}
    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    # 获取签名
    signs = _sign(uri, body)

    # 调用 API
    api_url = _API_HOST + uri
    headers = _build_headers(signs, a1)

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


def poll_qrcode(qr_id: str, code: str) -> dict:
    """轮询小红书扫码登录状态（和 B站一样的流程）。

    Returns:
        {
            "code_status": int,  # 0=未扫码, 1=已扫码, 2=成功, 3=失效
            "login_info": dict,  # 仅成功时有
            "cookies": dict,     # 仅成功时有
        }
    """
    a1 = get_a1()

    params = {"qr_id": qr_id, "code": code}
    uri = "/api/sns/web/v1/login/qrcode/status"

    # 获取签名（GET 请求，data=None）
    signs = _sign(uri, None)

    # 构建带参数的 URL
    query_str = urllib.parse.urlencode(params)
    api_url = _API_HOST + uri + "?" + query_str

    headers = _build_headers(signs, a1)

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
        # 合并 cookies：API 响应的 Set-Cookie + Playwright 浏览器中的完整 cookie
        merged = {"a1": a1}
        merged.update(resp_cookies)

        # 从 Playwright 浏览器获取完整 cookie（包含 webId、xsecappid 等）
        try:
            browser_cookies = get_browser_cookies()
            if browser_cookies:
                # 浏览器 cookie 优先级低于 API 响应（API 响应的是最新登录凭证）
                for k, v in browser_cookies.items():
                    if k not in merged:
                        merged[k] = v
                logger.info(f"从浏览器补充 Cookie: {list(browser_cookies.keys())}")
        except Exception as e:
            logger.warning(f"从浏览器获取 Cookie 失败: {e}")

        ret["cookies"] = merged
        logger.info(f"小红书扫码登录成功！获取到 {len(merged)} 个 Cookie: {list(merged.keys())}")
        _save_cookies(merged)

    return ret


def _save_cookies(cookies: dict) -> None:
    """保存 cookie 到 cookies_xhs.txt。"""
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    cookie_file = root / "cookies_xhs.txt"

    lines = []
    for key in ("a1", "web_session", "webId", "xsecappid", "abRequestId", "acw_tc"):
        if cookies.get(key):
            lines.append(f"{key}={cookies[key]}")

    cookie_file.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"小红书 Cookie 已保存到 {cookie_file}")

    # 清除 xhs_client 的 cookie 缓存
    try:
        from analysis import xhs_client
        xhs_client._cookies_cache = None
    except Exception:
        pass
