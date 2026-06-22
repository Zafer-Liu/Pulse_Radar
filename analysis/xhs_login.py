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
# Stealth 反检测脚本
# 小红书会检测 navigator.webdriver 等无头浏览器特征，
# 检测到后会重定向到登录页，即使注入了有效 Cookie 也会被拦截。
# 此脚本在每个页面加载前注入，隐藏自动化特征。
# ============================================================
_STEALTH_JS = """
// 1. 覆盖 navigator.webdriver（最关键）
Object.defineProperty(navigator, 'webdriver', {
    get: () => false,
    configurable: true,
});

// 2. 添加 window.chrome 对象
if (!window.chrome) {
    window.chrome = {
        runtime: {},
        app: { isInstalled: false },
        csi: () => {},
        loadTimes: () => {},
    };
}

// 3. 修改 navigator.plugins（模拟真实浏览器有插件）
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
        ];
        plugins.length = 3;
        return plugins;
    },
    configurable: true,
});

// 4. 修改 navigator.languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en-US', 'en'],
    configurable: true,
});

// 5. 修改 navigator.permissions.query
const originalQuery = window.navigator.permissions ? window.navigator.permissions.query : null;
if (originalQuery) {
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
}

// 6. 修改 WebGL 渲染器信息（隐藏虚拟显卡）
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) {
        return 'Intel Inc.'; // UNMASKED_VENDOR_WEBGL
    }
    if (parameter === 37446) {
        return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
    }
    return getParameter.call(this, parameter);
};

// 7. 修改 navigator.connection（模拟真实网络连接）
if (!navigator.connection) {
    Object.defineProperty(navigator, 'connection', {
        get: () => ({
            effectiveType: '4g',
            rtt: 50,
            downlink: 10,
            saveData: false,
        }),
        configurable: true,
    });
}

// 8. 隐藏 Playwright 自动化特征
delete window.__playwright__evaluator;
delete window.__pw_manual;

// 9. 修改 navigator.platform（与 UA 一致）
Object.defineProperty(navigator, 'platform', {
    get: () => 'Win32',
    configurable: true,
});

// 10. 添加 navigator.hardwareConcurrency
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
    configurable: true,
});

// 11. 添加 navigator.deviceMemory
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
    configurable: true,
});
"""

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
    """读取已保存的 cookie，返回 Playwright cookie 格式。

    读取顺序（合并，后者覆盖前者）：
        1. cookies_xhs.txt（本地文件）
        2. XHS_COOKIES 环境变量（整体 Cookie 字符串）
        3. XHS_A1 / XHS_WEB_SESSION 等单独环境变量

    这样 Railway 等云平台通过环境变量配置的 Cookie 也能被
    Playwright 签名服务使用，避免签名无效和登录墙问题。
    """
    import os
    from pathlib import Path

    cookie_dict: dict[str, str] = {}

    # 1. 从 cookies_xhs.txt 读取（本地文件）
    root = Path(__file__).resolve().parent.parent
    cookie_file = root / "cookies_xhs.txt"
    if cookie_file.exists():
        try:
            raw = cookie_file.read_text(encoding="utf-8").strip()
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                cookie_dict[key.strip()] = value.strip()
            logger.info(f"签名服务：从 cookies_xhs.txt 加载 {len(cookie_dict)} 个 Cookie")
        except Exception as e:
            logger.warning(f"签名服务：读取 cookies_xhs.txt 失败: {e}")

    # 2. 从 XHS_COOKIES 环境变量读取（整体 Cookie 字符串）
    xhs_cookies_str = os.environ.get("XHS_COOKIES", "").strip()
    if xhs_cookies_str:
        for pair in xhs_cookies_str.split(";"):
            pair = pair.strip()
            if "=" in pair:
                key, _, value = pair.partition("=")
                key = key.strip()
                value = value.strip()
                if key and value:
                    cookie_dict[key] = value
        logger.info(f"签名服务：从 XHS_COOKIES 环境变量加载，共 {len(cookie_dict)} 个字段")

    # 3. 从单独环境变量读取（覆盖同名字段）
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
            cookie_dict[cookie_key] = val
            env_loaded += 1
    if env_loaded > 0:
        logger.info(f"签名服务：从单独环境变量加载 {env_loaded} 个 Cookie")

    # 转换为 Playwright cookie 格式
    cookies = []
    for name, value in cookie_dict.items():
        cookies.append({
            "name": name,
            "value": value,
            "domain": ".xiaohongshu.com",
            "path": "/",
        })
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
        # 添加反检测启动参数，隐藏自动化特征
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors",
                "--ignore-certificate-errors-spki-list",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )
        context = browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 720},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        # 关键：添加 stealth 反检测脚本到 context
        # 这样所有新页面（包括评论提取的标签页）都会在加载前执行
        context.add_init_script(_STEALTH_JS)

        # 关键修复：先注入 Cookie，再访问页面
        # 如果先访问页面再注入 Cookie，小红书会将此会话标记为"未登录"，
        # 后续导航到笔记页面时会被重定向到登录页。
        # 先注入 Cookie，浏览器首次请求就携带登录态，服务器从一开始就认为是登录用户。
        saved_cookies = _load_saved_cookies()
        if saved_cookies:
            # 完善 Cookie 属性，确保被正确发送
            for c in saved_cookies:
                c["secure"] = True
                c["httpOnly"] = c["name"] in ("web_session", "a1")
                c["sameSite"] = "Lax"
            context.add_cookies(saved_cookies)
            logger.info(f"签名服务：已注入 {len(saved_cookies)} 个用户 Cookie（在页面加载前）")

        page = context.new_page()

        logger.info("签名服务：正在加载小红书页面...")
        page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # 检测签名服务页面是否被重定向到登录页
        init_url = page.url
        if "/login" in init_url:
            logger.warning(f"签名服务页面被重定向到登录页: {init_url}，stealth 可能未完全生效")
            # 尝试重新加载（stealth 脚本可能在第二次加载时生效）
            time.sleep(2)
            page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            if "/login" in page.url:
                logger.error("签名服务页面仍被重定向到登录页，签名功能可能不可用")
            else:
                logger.info(f"签名服务页面重载成功: {page.url}")
        else:
            logger.info(f"签名服务页面加载成功: {init_url}")

        # 验证 window._webmsxyw 是否存在（签名函数）
        try:
            has_sign_fn = page.evaluate("typeof window._webmsxyw === 'function'")
            if has_sign_fn:
                logger.info("签名服务：window._webmsxyw 签名函数可用")
            else:
                logger.error("签名服务：window._webmsxyw 不存在，签名将失败！页面可能未正确加载")
        except Exception as e:
            logger.warning(f"签名服务：检查 _webmsxyw 失败: {e}")

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
                    # _webmsxyw 返回 {X-s, X-t, X-s-common, ...}
                    # 把所有字段都返回，调用方按需使用
                    result = {}
                    for key, val in encrypt_params.items():
                        if val is not None:
                            # 转为小写 header 格式：X-s -> x-s, X-t -> x-t
                            result[key.lower()] = str(val)
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

                    # 带重试的导航：如果被重定向到登录页，等待后重试
                    # stealth 脚本可能需要页面加载一次后才完全生效
                    current_url = ""
                    for nav_attempt in range(3):
                        comment_page.goto(nav_url, wait_until="networkidle", timeout=30000)
                        current_url = comment_page.url
                        logger.info(f"评论页面导航完成 (attempt {nav_attempt + 1}/3): {current_url}")

                        # 检测是否被重定向到登录页
                        if "/login" not in current_url and "redirectPath" not in current_url:
                            break

                        logger.warning(f"评论页面被重定向到登录页 (attempt {nav_attempt + 1})，等待后重试")
                        if nav_attempt < 2:
                            time.sleep(3)
                            # 重新注入 Cookie，确保登录态
                            saved = _load_saved_cookies()
                            if saved:
                                for c in saved:
                                    c["secure"] = True
                                    c["httpOnly"] = c["name"] in ("web_session", "a1")
                                    c["sameSite"] = "Lax"
                                context.add_cookies(saved)

                    # 如果仍然被重定向到登录页，返回空结果
                    if "/login" in current_url or "redirectPath" in current_url:
                        logger.warning("评论页面重试 3 次仍被重定向到登录页，Cookie 可能已过期")
                        _result_queue.put({
                            "ok": True,
                            "result": {
                                "domComments": [],
                                "stateComments": [],
                                "domCount": 0,
                                "debug": {"title": "登录页", "url": current_url, "bodyLength": 0},
                                "loginRedirect": True,
                            },
                        })
                        continue

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

            elif cmd_type == "navigate_and_extract_search":
                # 导航到搜索页面，等待搜索结果加载，从 DOM 和 __INITIAL_STATE__ 提取
                # 搜索页面和笔记页面不同，通常不会被风控
                keyword = cmd[1]
                search_page = None
                try:
                    from urllib.parse import quote
                    search_url = f"https://www.xiaohongshu.com/search_result?keyword={quote(keyword)}&source=web_search_result_notes"
                    search_page = context.new_page()
                    # 用 domcontentloaded 而非 networkidle，搜索页面有持续网络请求，
                    # networkidle 会永远超时
                    search_page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                    current_url = search_page.url
                    logger.info(f"搜索页面导航完成: {current_url}")

                    # 检测是否被重定向到登录页
                    if "/login" in current_url or "redirectPath" in current_url:
                        logger.warning(f"搜索页面被重定向到登录页: {current_url}")
                        _result_queue.put({
                            "ok": True,
                            "result": {"results": [], "loginRedirect": True},
                        })
                        continue

                    # 等待搜索结果加载（等待特定元素出现，最多等 15 秒）
                    try:
                        search_page.wait_for_selector(
                            ".note-item, [class*='NoteCard'], [class*='note-item'], a[href*='/explore/'], .feeds-container, .search-result",
                            timeout=15000,
                        )
                        logger.info("搜索页面结果元素已出现")
                    except Exception:
                        logger.warning("搜索页面未检测到结果元素，继续尝试提取")

                    # 额外等待确保数据加载
                    time.sleep(2)
                    # 滚动加载更多
                    for _ in range(2):
                        try:
                            search_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        except Exception:
                            pass
                        time.sleep(1)

                    # 从 DOM 和 __INITIAL_STATE__ 提取搜索结果
                    js_extract_search = """
                    () => {
                        const results = [];

                        // 方法1：从 __INITIAL_STATE__ 提取（最可靠）
                        try {
                            const state = window.__INITIAL_STATE__;
                            if (state) {
                                // 搜索结果可能在多个位置
                                let searchNotes = null;
                                if (state.search) {
                                    if (state.search.notes) searchNotes = state.search.notes;
                                    else if (state.search.feeds) searchNotes = state.search.feeds;
                                    else if (state.search.searchNotes) {
                                        searchNotes = state.search.searchNotes.notes || state.search.searchNotes.feeds;
                                    }
                                }
                                if (searchNotes && Array.isArray(searchNotes)) {
                                    searchNotes.forEach(item => {
                                        const note = item.note_card || item.model_type ? item : (item.note || item);
                                        if (!note) return;
                                        const noteId = note.note_id || note.id || note.noteId || '';
                                        if (!noteId) return;
                                        const user = note.user || {};
                                        const interact = note.interact_info || note.interactInfo || {};
                                        results.push({
                                            id: noteId,
                                            title: note.title || note.display_title || '',
                                            desc: (note.desc || note.display_desc || '').substring(0, 100),
                                            type: note.type === 'video' ? 'video' : 'image',
                                            user: {
                                                userId: user.user_id || user.userId || '',
                                                nickname: user.nickname || user.nick_name || '',
                                                avatar: user.avatar || '',
                                            },
                                            interactInfo: {
                                                likes: interact.liked_count || interact.likedCount || '0',
                                                commentCount: interact.comment_count || interact.commentCount || '0',
                                            },
                                            xsecToken: note.xsec_token || note.xsecToken || '',
                                            time: note.time || 0,
                                        });
                                    });
                                }
                            }
                        } catch(e) {
                            console.log('extract from state error:', e);
                        }

                        // 方法2：从 DOM 提取（备选）
                        if (results.length === 0) {
                            const selectors = [
                                '.note-item',
                                '[class*="NoteCard"]',
                                '[class*="note-item"]',
                                '.search-result-item',
                                'section.note-item',
                                'a[href*="/explore/"]',
                            ];
                            let items = [];
                            for (const sel of selectors) {
                                items = document.querySelectorAll(sel);
                                if (items.length > 0) break;
                            }
                            items.forEach(item => {
                                try {
                                    const linkEl = item.querySelector('a[href*="/explore/"]') || item;
                                    const href = linkEl.href || '';
                                    const noteIdMatch = href.match(/\\/explore\\/([a-f0-9]+)/);
                                    const noteId = noteIdMatch ? noteIdMatch[1] : '';
                                    if (!noteId) return;
                                    const titleEl = item.querySelector('.title, [class*="title"], .note-title, .desc');
                                    const authorEl = item.querySelector('.author, .name, [class*="author"], [class*="name"]');
                                    const likeEl = item.querySelector('.like-wrapper .count, [class*="like"] [class*="count"]');
                                    results.push({
                                        id: noteId,
                                        title: titleEl ? titleEl.textContent.trim() : '',
                                        desc: '',
                                        type: 'image',
                                        user: {
                                            userId: '',
                                            nickname: authorEl ? authorEl.textContent.trim() : '',
                                            avatar: '',
                                        },
                                        interactInfo: {
                                            likes: likeEl ? likeEl.textContent.trim() : '0',
                                            commentCount: '0',
                                        },
                                        xsecToken: '',
                                        time: 0,
                                    });
                                } catch(e) {}
                            });
                        }

                        return {
                            results: results,
                            debug: {
                                title: document.title,
                                url: window.location.href,
                                bodyLength: document.body.innerHTML.length,
                            },
                        };
                    }
                    """
                    result = search_page.evaluate(js_extract_search)
                    dbg = result.get("debug", {})
                    results = result.get("results", [])
                    logger.info(
                        f"搜索结果提取: results={len(results)}, "
                        f"page={dbg.get('title', '?')}, bodyLen={dbg.get('bodyLength', 0)}"
                    )
                    _result_queue.put({"ok": True, "result": result})
                except Exception as e:
                    logger.warning(f"navigate_and_extract_search 失败: {e}")
                    _result_queue.put({"ok": False, "error": str(e)})
                finally:
                    if search_page:
                        try:
                            search_page.close()
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
                    logger.info(f"浏览器 fetch 开始: method={fetch_method} url={fetch_url}")
                    if fetch_body:
                        logger.info(f"浏览器 fetch body: {fetch_body}")
                    # 使用 window._webmsxyw() 生成签名，然后带签名发起 fetch
                    # 这样一个命令就完成签名+请求，避免签名队列超时
                    js_code = """
                    async ([url, method, body]) => {
                        // 生成签名
                        let signData = null;
                        let signKeys = [];
                        try {
                            const path = new URL(url).pathname + new URL(url).search;
                            const webmsxyw = window._webmsxyw;
                            if (webmsxyw) {
                                signData = webmsxyw(path, method === 'POST' ? body : undefined);
                                if (signData) {
                                    signKeys = Object.keys(signData);
                                }
                            } else {
                                return { status: -1, body: 'ERROR: window._webmsxyw not found' };
                            }
                        } catch(e) {
                            return { status: -2, body: 'ERROR sign: ' + e.message };
                        }

                        const opts = {
                            method: method,
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'Content-Type': 'application/json',
                            }
                        };
                        // 添加签名头（X-s, X-t, X-s-common 等）
                        if (signData) {
                            // _webmsxyw 返回 {X-s, X-t, X-s-common, ...}
                            // 把所有字段都添加到请求头
                            for (const key in signData) {
                                if (signData[key] != null) {
                                    opts.headers[key] = String(signData[key]);
                                }
                            }
                        }
                        if (body && method === 'POST') {
                            opts.body = JSON.stringify(body);
                        }
                        try {
                            const resp = await fetch(url, opts);
                            const text = await resp.text();
                            return { status: resp.status, body: text, signKeys: signKeys };
                        } catch(e) {
                            return { status: -3, body: 'ERROR fetch: ' + e.message, signKeys: signKeys };
                        }
                    }
                    """
                    result = page.evaluate(js_code, [fetch_url, fetch_method, fetch_body])
                    sign_keys = result.get("signKeys", []) if isinstance(result, dict) else []
                    logger.info(f"浏览器 fetch 签名字段: {sign_keys}")
                    logger.info(f"浏览器 fetch 结果: status={result.get('status')}, body 长度={len(result.get('body', ''))}")
                    _result_queue.put({"ok": True, "result": result})
                except Exception as e:
                    logger.warning(f"浏览器 fetch 失败: {e}", exc_info=True)
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
        result = _result_queue.get(timeout=30)
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


def extract_search_results(keyword: str) -> dict:
    """导航到搜索页面，等待搜索结果加载，从 DOM 和 __INITIAL_STATE__ 提取搜索结果。

    搜索页面和笔记页面不同，通常不会被风控。
    这是对搜索 API 被风控（code=-104/-300011）时的备选方案。

    Args:
        keyword: 搜索关键词

    Returns:
        {"results": list, "debug": dict}
    """
    if not _ensure_worker():
        raise RuntimeError("签名服务不可用（Playwright 未安装或启动失败）")

    _cmd_queue.put(("navigate_and_extract_search", keyword))
    try:
        result = _result_queue.get(timeout=60)
        if result.get("ok"):
            return result["result"]
        raise RuntimeError(f"提取搜索结果失败: {result.get('error', '未知错误')}")
    except queue.Empty:
        raise RuntimeError("提取搜索结果超时")


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
