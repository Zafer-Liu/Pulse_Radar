#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
声浪雷达真实版：本地后端服务

功能：
1. 解析 B站普通链接和 b23.tv 短链
2. 获取真实视频公开信息
3. 抓取真实公开评论
4. 做轻量级本地舆情分析
5. 提供前端页面和 /api/analyze 接口

说明：
- 不使用模拟数据。
- 只访问公开网页和公开接口。
- 如果 B站接口要求登录、风控或限流，接口会返回明确错误。
"""

from __future__ import annotations

import copy
import hashlib
import http.cookiejar
import json
import logging
import logging.handlers
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

# P2 分析质量升级：jieba 分词 + Hownet/NTUSD/清华三库情感词典 + 程度词加权 + 否定词翻转。
# 缺 jieba 时自动降级为旧子串匹配，保证服务可启动。
try:
    from analysis.lexicon import (
        tokenize as _lex_tokenize,
        extract_tags as _lex_extract_tags,
        POSITIVE as _lex_positive,
        NEGATIVE as _lex_negative,
        DEGREE as _lex_degree,
        DENIAL_WORDS as _lex_denial,
        warmup as _lexicon_warmup,
    )
    _LEXICON_OK = True
except Exception as _lex_exc:  # noqa: BLE001
    _LEXICON_OK = False
    logging.getLogger("lexicon").warning(
        "analysis.lexicon 加载失败(%s)，情感分析将降级为子串匹配。"
        "请用 .venv 运行：.venv/Scripts/python server.py", _lex_exc,
    )
    _lex_tokenize = None  # type: ignore
    _lex_extract_tags = None  # type: ignore
    _lex_positive = lambda: frozenset()  # type: ignore
    _lex_negative = lambda: frozenset()  # type: ignore
    _lex_degree = lambda: {}  # type: ignore
    _lex_denial = frozenset()  # type: ignore
    _lexicon_warmup = lambda: None  # type: ignore

# LLM 报告模块（OpenAI 兼容协议，默认 DeepSeek）
# 关键：先加载 .env 文件，否则 llm_report.py 在 import 时读 os.environ 会拿不到配置
def _load_env_file() -> None:
    """从项目根目录 .env 文件加载环境变量（零依赖，不覆盖已存在的环境变量）。"""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception as exc:
        logging.getLogger("env").warning(f"加载 .env 失败：{exc}")

_load_env_file()

try:
    from analysis import xhs_client
except Exception as _xhs_exc:  # noqa: BLE001
    xhs_client = None  # type: ignore
    logging.getLogger("xhs_client").debug("analysis.xhs_client 加载失败(%s)，小红书功能不可用。", _xhs_exc)

try:
    from analysis import xhs_login
except Exception as _xhs_login_exc:  # noqa: BLE001
    xhs_login = None  # type: ignore
    logging.getLogger("xhs_login").debug("analysis.xhs_login 加载失败(%s)，小红书扫码登录不可用。", _xhs_login_exc)

try:
    from analysis.llm_report import generate_report as _llm_generate_report, is_available as _llm_available
except Exception as _llm_exc:  # noqa: BLE001
    _llm_generate_report = None  # type: ignore
    _llm_available = lambda: False  # type: ignore
    logging.getLogger("llm_report").debug("analysis.llm_report 加载失败(%s)，报告将用纯模板。", _llm_exc)

# LLM 增强情感分析（可选模块，对词典法判为"中性"的评论做二次分类）
# 复用 llm_report 的 LLM 通道，零新增依赖。无 key 或 import 失败时降级为纯词典法。
try:
    from analysis.llm_sentiment import enhance_neutral_comments, is_available as _llm_sentiment_available
    _LLM_SENTIMENT_OK = _llm_sentiment_available()
except Exception as _llm_sent_exc:  # noqa: BLE001
    enhance_neutral_comments = None  # type: ignore
    _llm_sentiment_available = lambda: False  # type: ignore
    _LLM_SENTIMENT_OK = False
    logging.getLogger("llm_sentiment").debug("analysis.llm_sentiment 加载失败(%s)，情感增强将跳过。", _llm_sent_exc)


# LLM 配置文件路径
ENV_FILE = Path(__file__).resolve().parent / ".env"

# .env 中支持的 LLM 字段（顺序即写入顺序）
_LLM_ENV_KEYS = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "LLM_TIMEOUT"]

# Webhook 告警相关环境变量
_ALERT_ENV_KEYS = ["ALERT_WEBHOOK_URL", "ALERT_MIN_RISK", "ALERT_COOLDOWN_SEC"]

# 预设 provider（前端"一键填入"按钮用）
LLM_PRESETS = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "label": "DeepSeek"},
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash", "label": "智谱 GLM"},
    "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-turbo", "label": "通义千问"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "label": "OpenAI"},
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:7b", "label": "本地 Ollama"},
}


def _read_env_file() -> dict[str, str]:
    """读取 .env 文件，返回 dict（不污染 os.environ）。文件不存在返回空 dict。"""
    if not ENV_FILE.exists():
        return {}
    result: dict[str, str] = {}
    try:
        for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip().strip('"').strip("'")
    except Exception as exc:
        logger.warning(f"读取 .env 失败：{exc}")
    return result


def _write_env_file(updates: dict[str, str], group_comment: str = "") -> None:
    """写入 .env 文件。保留已有非 updates 字段和注释，updates 中的字段用新值覆盖。
    updates 中 key 为空字符串表示删除该字段。
    group_comment: 追加新 key 时写的分组注释（如 "# LLM 配置"）。
    """
    existing_lines: list[str] = []
    if ENV_FILE.exists():
        existing_lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    # 收集已存在的 key -> 行号
    seen_keys: set[str] = set()
    new_lines: list[str] = []
    pending_updates = dict(updates)  # 副本，写过的从里面删
    update_keys = set(updates.keys())

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in update_keys:
                seen_keys.add(key)
                if key in pending_updates:
                    val = pending_updates.pop(key)
                    if val:  # 非空，写入新值
                        new_lines.append(f'{key}={val}')
                    # 空字符串则跳过（删除该行）
                else:
                    # 不在 updates 里，保留原行
                    new_lines.append(line)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # 追加未处理的新 key
    if pending_updates:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        if group_comment:
            new_lines.append(group_comment)
        for key, val in pending_updates.items():
            if val:
                new_lines.append(f'{key}={val}')

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _reload_llm_module() -> bool:
    """重新加载 analysis.llm_report 与 analysis.llm_sentiment 模块，让新配置生效。
    返回 True 表示重载成功且 LLM 可用。
    """
    global _llm_generate_report, _llm_available, _LLM_SENTIMENT_OK, enhance_neutral_comments
    try:
        import importlib
        from analysis import llm_report as _llm_mod
        from analysis import llm_sentiment as _llm_sent_mod
        # 先把新 .env 注入 os.environ（_load_env_file 不覆盖已存在，所以手动 set）
        env_map = _read_env_file()
        for key in _LLM_ENV_KEYS:
            if key in env_map:
                os.environ[key] = env_map[key]
        importlib.reload(_llm_mod)
        importlib.reload(_llm_sent_mod)
        _llm_generate_report = _llm_mod.generate_report
        _llm_available = _llm_mod.is_available
        enhance_neutral_comments = _llm_sent_mod.enhance_neutral_comments
        _LLM_SENTIMENT_OK = _llm_sent_mod.is_available()
        return bool(_llm_available())
    except Exception as exc:
        logger.warning(f"重载 llm 模块失败：{exc}")
        return False


ROOT = Path(__file__).resolve().parent
# Railway/容器化部署通过 PORT 环境变量注入端口；本地默认 8088
PORT = int(os.environ.get("PORT", "8088"))
DATA_FILE = ROOT / "data.json"
DATA_LOCK = threading.RLock()
LOG_FILE = ROOT / "server.log"


def setup_logger() -> logging.Logger:
    log = logging.getLogger("shenglang")
    if log.handlers:
        return log
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    log.addHandler(console)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        log.addHandler(file_handler)
    except Exception as exc:
        log.warning(f"日志文件无法初始化：{exc}")
    log.propagate = False

    # 为子模块 logger 添加相同的 handler，使 xhs_client/xhs_login 等日志也能输出
    for sub_name in ("xhs_client", "xhs_login", "xhs_sign", "lexicon", "llm_report", "llm_sentiment", "alert", "agent_core"):
        sub_log = logging.getLogger(sub_name)
        sub_log.setLevel(logging.DEBUG)
        sub_log.addHandler(console)
        try:
            sub_log.addHandler(file_handler)
        except Exception:
            pass
        sub_log.propagate = False

    return log


logger = setup_logger()


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


COOKIE_JAR = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(COOKIE_JAR))
SESSION_LOCK = threading.Lock()
SESSION_READY = False
COOKIE_FILE = ROOT / "cookies.txt"


def _set_cookie(name: str, value: str) -> None:
    if not value:
        return
    ck = http.cookiejar.Cookie(
        version=0, name=name, value=value,
        port=None, port_specified=False,
        domain=".bilibili.com", domain_specified=True, domain_initial_dot=True,
        path="/", path_specified=True, secure=False, expires=None,
        discard=False, comment=None, comment_url=None, rest={},
    )
    COOKIE_JAR.set_cookie(ck)


def load_user_cookies() -> dict[str, str]:
    """从环境变量或 cookies.txt 加载用户登录 Cookie，主要是 SESSDATA。"""
    import os
    found: dict[str, str] = {}
    for key in ("SESSDATA", "bili_jct", "DedeUserID", "buvid3"):
        val = os.environ.get(key) or os.environ.get(f"BILI_{key}")
        if val:
            found[key] = val.strip()
    if COOKIE_FILE.exists():
        try:
            text = COOKIE_FILE.read_text(encoding="utf-8")
            for raw in text.replace(";", "\n").splitlines():
                raw = raw.strip()
                if not raw or raw.startswith("#"):
                    continue
                if "=" not in raw:
                    continue
                k, v = raw.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k:
                    found[k] = v
        except Exception as exc:
            logger.warning(f"读取 cookies.txt 失败：{exc}")
    return found


def bootstrap_session(force: bool = False) -> None:
    """访问 B 站首页，拿到 buvid3 等指纹 Cookie，并注入用户 SESSDATA（如果配置了）。"""
    global SESSION_READY
    with SESSION_LOCK:
        if SESSION_READY and not force:
            return
        try:
            req = urllib.request.Request("https://www.bilibili.com/", headers=HEADERS)
            with OPENER.open(req, timeout=15) as resp:
                resp.read(2048)
            cookie_names = sorted({c.name for c in COOKIE_JAR})
            logger.info(f"已建立 B站会话，Cookie：{cookie_names}")
            if "buvid3" not in cookie_names:
                req2 = urllib.request.Request(
                    "https://api.bilibili.com/x/frontend/finger/spi", headers=HEADERS
                )
                with OPENER.open(req2, timeout=15) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                try:
                    spi = json.loads(body).get("data", {})
                    buvid3 = spi.get("b_3")
                    if buvid3:
                        _set_cookie("buvid3", buvid3)
                        logger.info(f"通过 finger/spi 注入 buvid3=...{buvid3[-6:]}")
                except Exception as exc:
                    logger.warning(f"finger/spi 解析失败：{exc}")
            # 注入用户 Cookie（SESSDATA 等），用于绕开未登录评论限流
            user_cookies = load_user_cookies()
            for name, value in user_cookies.items():
                _set_cookie(name, value)
            if "SESSDATA" in user_cookies:
                logger.info(
                    f"已注入登录 Cookie：SESSDATA=...{user_cookies['SESSDATA'][-6:]}（启用完整评论抓取）"
                )
            else:
                logger.warning(
                    "未配置 SESSDATA，B站会限制未登录请求只返回 3 条精选评论。"
                    "请在 cookies.txt 或环境变量 SESSDATA 中配置浏览器登录态。"
                )
            SESSION_READY = True
        except Exception as exc:
            logger.warning(f"建立 B站会话失败：{exc}")


# ---- WBI 签名（B 站近年评论/搜索接口的强制签名机制） ----
WBI_KEY_LOCK = threading.Lock()
WBI_KEYS: dict[str, Any] = {"img": "", "sub": "", "mixin": "", "fetched_at": 0}

# B 站固定的字符重排表（和 wbi.js 保持一致）
WBI_MIXIN_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in WBI_MIXIN_TABLE if i < len(orig))[:32]


def get_wbi_keys(force: bool = False) -> tuple[str, str]:
    """从 nav 接口取 img_key / sub_key，并缓存 30 分钟。"""
    with WBI_KEY_LOCK:
        if (
            not force
            and WBI_KEYS["mixin"]
            and time.time() - WBI_KEYS["fetched_at"] < 1800
        ):
            return WBI_KEYS["img"], WBI_KEYS["sub"]
        bootstrap_session()
        try:
            data = http_get_json("https://api.bilibili.com/x/web-interface/nav")
            wbi = (data.get("data") or {}).get("wbi_img") or {}
            img_url = wbi.get("img_url") or ""
            sub_url = wbi.get("sub_url") or ""
            img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
            sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
            mixin = _get_mixin_key(img_key + sub_key)
            WBI_KEYS.update(
                {"img": img_key, "sub": sub_key, "mixin": mixin, "fetched_at": time.time()}
            )
            logger.info(
                f"获取 WBI 密钥：img={img_key[:8]}... sub={sub_key[:8]}... mixin={mixin[:8]}..."
            )
            return img_key, sub_key
        except Exception as exc:
            logger.warning(f"获取 WBI 密钥失败：{exc}")
            return "", ""


def wbi_sign(params: dict[str, Any]) -> dict[str, Any]:
    """对参数做 WBI 签名，返回带 wts/w_rid 的新参数 dict。"""
    get_wbi_keys()
    mixin = WBI_KEYS.get("mixin") or ""
    signed = {k: v for k, v in params.items() if v is not None}
    signed["wts"] = int(time.time())
    # 按 key 字典序排序
    items = sorted(signed.items(), key=lambda kv: kv[0])
    # 过滤特殊字符
    sanitized = []
    bad_chars = "!'()*"
    for k, v in items:
        sv = str(v)
        for ch in bad_chars:
            sv = sv.replace(ch, "")
        sanitized.append((k, sv))
    query = urllib.parse.urlencode(sanitized)
    signed["w_rid"] = hashlib.md5((query + mixin).encode("utf-8")).hexdigest()
    return signed


POSITIVE_WORDS = [
    "好看", "优秀", "喜欢", "支持", "厉害", "牛", "震撼", "感动", "创意",
    "用心", "绝了", "佩服", "高质量", "舒服", "清晰", "有趣", "惊艳",
    "期待", "赞", "神", "细节", "真诚", "好评", "可以", "不错",
]

NEGATIVE_WORDS = [
    "不好", "失望", "无聊", "尴尬", "难受", "离谱", "差", "烂", "贵",
    "涨价", "少了", "退步", "敷衍", "质疑", "不行", "问题", "割韭菜",
    "不值", "下降", "骗", "反感", "恶心", "崩", "糟糕", "不透明",
]

RISK_WORDS = [
    "投诉", "举报", "维权", "抵制", "退钱", "退款", "道歉", "曝光",
    "诈骗", "侵权", "抄袭", "造假", "黑幕", "上热搜", "舆论", "校方",
    "学生会", "处罚", "法律", "监管", "315",
]

CONTROVERSY_WORDS = [
    "但是", "不过", "虽然", "理性", "争议", "一方面", "另一方面",
    "不好说", "看情况", "也许", "未必", "各有", "怎么说",
]

TOPIC_RULES = {
    "内容创意": ["创意", "想法", "脑洞", "动画", "设计", "形式", "剪辑", "技术"],
    "制作质量": ["质量", "细节", "用心", "画面", "镜头", "效果", "完成度", "质感"],
    "情感共鸣": ["感动", "泪目", "青春", "回忆", "共鸣", "热血", "喜欢", "真诚"],
    "价格与成本": ["涨价", "价格", "贵", "便宜", "成本", "补贴", "饭钱", "生活费"],
    "质量质疑": ["少了", "变差", "下降", "缩水", "难吃", "不新鲜", "敷衍"],
    "透明沟通": ["透明", "说明", "公开", "沟通", "解释", "原因", "座谈", "听证"],
    "风险行动": ["投诉", "举报", "维权", "抵制", "学生会", "道歉", "曝光", "退款"],
}


def now_ts() -> int:
    return int(time.time())


def fmt_ts(ts: int | float | None = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or time.time()))


def interval_seconds(value: int | str, unit: str) -> int:
    try:
        number = max(1, int(value))
    except Exception:
        number = 1
    return number * (86400 if unit == "天" else 3600)


def default_db() -> dict[str, Any]:
    return {"version": 1, "monitors": []}


# 内存缓存：避免每次请求都读盘 + json.loads。save_db 写盘后同步更新缓存。
# 首次 load_db 后磁盘 IO 只发生在写操作，读请求全部走内存。
_DB_CACHE: dict[str, Any] | None = None


def load_db() -> dict[str, Any]:
    global _DB_CACHE
    with DATA_LOCK:
        if _DB_CACHE is None:
            if not DATA_FILE.exists():
                _DB_CACHE = default_db()
            else:
                try:
                    _DB_CACHE = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                    if "monitors" not in _DB_CACHE:
                        _DB_CACHE["monitors"] = []
                except Exception:
                    _DB_CACHE = default_db()
        # 返回深拷贝：现有代码采用 load→改字段→save 模式，调用方会就地修改返回对象。
        # 深拷贝隔离未提交的中间状态，避免污染缓存、避免并发请求互相干扰。
        return copy.deepcopy(_DB_CACHE)


def save_db(data: dict[str, Any]) -> None:
    global _DB_CACHE
    with DATA_LOCK:
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(DATA_FILE)
        _DB_CACHE = copy.deepcopy(data)


def public_monitor(monitor: dict[str, Any]) -> dict[str, Any]:
    item = dict(monitor)
    history = item.get("history") or []
    item["historyCount"] = len(history)
    item["history"] = history[:5]
    # 确保 lastResult 包含 sentiments 和 keywords（供前端趋势图使用）
    last_result = item.get("lastResult")
    if last_result and "sentiments" not in last_result:
        # lastResult 是 result_summary 的输出，已包含 sentiments/keywords；
        # 此处兜底：如果旧数据缺失，从最近一条 history 补充
        for entry in history[:1]:
            full = entry.get("result") or {}
            if full.get("sentiments"):
                last_result["sentiments"] = full["sentiments"]
            if full.get("keywords"):
                last_result["keywords"] = full["keywords"]
    return item


def _get_up_trend(author: str, limit: int = 5) -> list[dict[str, Any]]:
    """获取某个 UP 主（author）所有监测视频的历史情绪趋势。"""
    data = load_db()
    monitors = data.get("monitors", [])
    results = []
    for m in monitors:
        if m.get("author") != author:
            continue
        history = m.get("history", [])
        for entry in history[:limit]:
            result = entry.get("result", {})
            if not result:
                continue
            results.append({
                "monitorId": m.get("id"),
                "title": result.get("title", m.get("title", "")),
                "bvid": result.get("bvid", m.get("bvid", "")),
                "fetchedAt": entry.get("finishedAt", ""),
                "commentCount": result.get("commentCount", 0),
                "sentiments": result.get("sentiments", {}),
                "risk": result.get("risk", "unknown"),
                "keywords": result.get("keywords", [])[:5],
            })
    # 按时间排序
    results.sort(key=lambda x: x.get("fetchedAt", ""), reverse=True)
    return results[:limit]


def _get_topic_trend(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    """获取某个关键词相关的历史分析趋势（从所有监测任务中搜索标题匹配）。"""
    data = load_db()
    monitors = data.get("monitors", [])
    results = []
    kw_lower = keyword.lower()
    for m in monitors:
        title = (m.get("title") or "").lower()
        if kw_lower not in title:
            continue
        history = m.get("history", [])
        for entry in history[:3]:
            result = entry.get("result", {})
            if not result:
                continue
            results.append({
                "monitorId": m.get("id"),
                "title": result.get("title", m.get("title", "")),
                "bvid": result.get("bvid", m.get("bvid", "")),
                "fetchedAt": entry.get("finishedAt", ""),
                "commentCount": result.get("commentCount", 0),
                "sentiments": result.get("sentiments", {}),
                "risk": result.get("risk", "unknown"),
                "keywords": result.get("keywords", [])[:5],
            })
    results.sort(key=lambda x: x.get("fetchedAt", ""), reverse=True)
    return results[:limit]


def _get_monitor_history_for_agent(monitor_id: str) -> list[dict[str, Any]]:
    """为 Agent 工具提供监测任务的历史快照数据。"""
    data = load_db()
    monitor = None
    for m in data.get("monitors", []):
        if m.get("id") == monitor_id:
            monitor = m
            break
    if not monitor:
        return []
    history = monitor.get("history", [])
    results = []
    for entry in history[:10]:
        result = entry.get("result", {})
        if result:
            results.append({
                "fetchedAt": entry.get("finishedAt", ""),
                "sentiments": result.get("sentiments", {}),
                "risk": result.get("risk", "unknown"),
                "commentCount": result.get("commentCount", 0),
                "keywords": result.get("keywords", [])[:8],
                "topNegComments": [c.get("text", "")[:100] for c in (result.get("comments") or []) if c.get("sentiment") in ("neg", "risk")][:3],
            })
    return results


def http_get_text(url: str, params: dict[str, Any] | None = None) -> tuple[str, str]:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    logger.debug(f"GET {url}")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with OPENER.open(req, timeout=20) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset, errors="replace")
            logger.debug(f"<- {resp.status} {resp.geturl()} ({len(body)}B)")
            return body, resp.geturl()
    except urllib.error.HTTPError as exc:
        logger.warning(f"HTTPError {exc.code} for {url}")
        raise
    except Exception as exc:
        logger.warning(f"GET 失败 {url}：{exc}")
        raise


def http_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    body, _ = http_get_text(url, params)
    return json.loads(body)


def _is_allowed_image_host(host: str) -> bool:
    host = (host or "").lower()
    allowed_hosts = ("hdslb.com", "bilibili.com", "bilivideo.com", "sns-webpic-qc.xhscdn.com", "ci.xiaohongshu.com")
    return any(host == h or host.endswith("." + h) for h in allowed_hosts)


def http_get_binary(url: str, params: dict[str, Any] | None = None) -> tuple[bytes, str]:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    if url.startswith("//"):
        url = "https:" + url
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        raise ValueError("图片地址协议不支持。")
    if not _is_allowed_image_host(host):
        raise ValueError(f"不允许代理该图片域名：{host}")
    headers = dict(HEADERS)
    headers.update({
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://www.bilibili.com/",
    })
    logger.debug(f"代理图片 GET {url}")
    req = urllib.request.Request(url, headers=headers)

    # SSRF 防护：禁用自动重定向，逐跳校验目标 host，防止白名单域名 302 到内网/任意地址。
    # 同时对最终落地 URL 再校验一次（覆盖所有重定向路径）。
    class _SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            np = urllib.parse.urlparse(newurl)
            if np.scheme not in ("http", "https"):
                logger.warning(f"图片代理拒绝非 http(s) 重定向：{newurl}")
                return None
            if not _is_allowed_image_host(np.hostname or ""):
                logger.warning(f"图片代理拒绝重定向到非白名单域名：{np.hostname}")
                return None
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    safe_opener = urllib.request.build_opener(_SafeRedirect)
    with safe_opener.open(req, timeout=20) as resp:
        final_url = resp.geturl()
        final_host = (urllib.parse.urlparse(final_url).hostname or "").lower()
        if not _is_allowed_image_host(final_host):
            raise ValueError(f"图片最终地址域名不在白名单：{final_host}")
        content_type = resp.headers.get("Content-Type") or "image/jpeg"
        body = resp.read(8 * 1024 * 1024)
        logger.debug(f"图片代理完成：{final_url} ({len(body)}B, {content_type})")
        return body, content_type


def resolve_bvid(raw_url: str) -> tuple[str, str]:
    raw_url = raw_url.strip()
    if not raw_url:
        raise ValueError("请先输入 B站视频链接。")

    direct = re.search(r"(BV[0-9A-Za-z]+)", raw_url)
    if direct:
        logger.info(f"直接从输入识别到 BV 号：{direct.group(1)}")
        return raw_url, direct.group(1)

    logger.info(f"解析短链/外链：{raw_url}")
    body, final_url = http_get_text(raw_url)
    found = re.search(r"/video/(BV[0-9A-Za-z]+)", final_url) or re.search(r"(BV[0-9A-Za-z]+)", body)
    if not found:
        raise ValueError(f"无法从链接解析 BV 号，最终地址：{final_url}")
    logger.info(f"短链解析到 BV：{found.group(1)}（最终 URL：{final_url}）")
    return final_url, found.group(1)


def fetch_video_info(bvid: str) -> dict[str, Any]:
    logger.info(f"获取视频信息：{bvid}")
    data = http_get_json("https://api.bilibili.com/x/web-interface/view", {"bvid": bvid})
    if data.get("code") != 0:
        logger.error(f"视频信息接口异常：{data}")
        raise RuntimeError(f"视频信息接口返回异常：{data.get('message') or data}")
    info = data["data"]
    stat = info.get("stat") or {}
    logger.info(
        f"视频信息：title={info.get('title')!r} aid={info.get('aid')} "
        f"播放={stat.get('view')} 评论={stat.get('reply')}"
    )
    return info


def _try_legacy_reply(aid: int, page: int, sort: int = 2) -> dict[str, Any]:
    """旧版翻页接口（按页码）。ps 上限为 20，sort=2 按热度，sort=0 按时间。"""
    return http_get_json(
        "https://api.bilibili.com/x/v2/reply",
        {
            "jsonp": "jsonp",
            "pn": page,
            "ps": 20,
            "type": 1,
            "oid": aid,
            "sort": sort,
            "nohot": 0,
        },
    )


def _try_main_reply(aid: int, next_cursor: int, mode: int = 3) -> dict[str, Any]:
    """新版游标接口 /x/v2/reply/main，mode=3 按热度，mode=2 按时间。"""
    return http_get_json(
        "https://api.bilibili.com/x/v2/reply/main",
        {
            "jsonp": "jsonp",
            "next": next_cursor,
            "type": 1,
            "oid": aid,
            "mode": mode,
            "plat": 1,
            "ps": 30,
            "seek_rpid": "",
        },
    )


def _try_wbi_main_reply(aid: int, pagination_str: str = '{"offset":""}', mode: int = 3) -> dict[str, Any]:
    """带 WBI 签名的 /x/v2/reply/wbi/main 接口。这是 B 站当前 web 真正使用的接口。

    游标机制：B站要求回传上一页响应里 data.cursor.pagination_str 给下一页，
    自己构造的 offset 几乎无法被识别（会导致每页都返回第一页数据）。
    """
    raw_params = {
        "oid": aid,
        "type": 1,
        "mode": mode,
        "pagination_str": pagination_str,
        "plat": 1,
        "seek_rpid": "",
        "web_location": 1315875,
    }
    signed = wbi_sign(raw_params)
    return http_get_json("https://api.bilibili.com/x/v2/reply/wbi/main", signed)


def fetch_replies(aid: int, pages: int = 5) -> list[dict[str, Any]]:
    """抓取 B 站公开评论。

    顺序：
    1. 带 WBI 签名的 `/x/v2/reply/wbi/main` 游标接口（B 站当前 web 主用接口）。
    2. 如果 wbi 接口失败或拿不满，再走旧版 `/x/v2/reply` 翻页接口（先按热度，再按时间）。
    3. 都失败时退回未签名的 `/x/v2/reply/main` 接口（通常只能拿到 3 条精选）。
    """
    bootstrap_session()

    pages = max(1, min(int(pages or 5), 30))
    seen_rpids: set[int] = set()
    replies: list[dict[str, Any]] = []

    def absorb(items: list[dict[str, Any]]) -> int:
        added = 0
        for item in items or []:
            rpid = item.get("rpid")
            if rpid and rpid in seen_rpids:
                continue
            if rpid:
                seen_rpids.add(rpid)
            member = item.get("member") or {}
            content = item.get("content") or {}
            message = (content.get("message") or "").strip()
            if not message:
                continue
            replies.append(
                {
                    "user": member.get("uname") or "匿名用户",
                    "mid": member.get("mid"),
                    "text": message,
                    "likes": item.get("like", 0),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item.get("ctime", 0))),
                    "rpid": rpid,
                }
            )
            added += 1
        return added

    # ---- 1) WBI 签名的 main 接口（最关键的真实接口） ----
    wbi_failed = False
    pagination_str = '{"offset":""}'  # 第一页用空 offset；后续回传 B站给的 pagination_str
    for page_idx in range(1, pages + 1):
        try:
            data = _try_wbi_main_reply(aid, pagination_str)
        except Exception as exc:
            logger.warning(f"[wbi main] 第 {page_idx} 页请求异常：{exc}")
            wbi_failed = True
            break
        code = data.get("code")
        msg = data.get("message")
        d = data.get("data") or {}
        cursor = d.get("cursor") or {}
        top = d.get("top") or {}
        top_replies = (top.get("upper") and [top["upper"]] or []) + (top.get("admin") and [top["admin"]] or []) + (d.get("top_replies") or [])
        page_replies = d.get("replies") or []
        is_end = bool(cursor.get("is_end"))
        all_count = cursor.get("all_count")
        next_num = cursor.get("next")  # 仅用于日志，真正用于翻页的是 pagination_str
        # 关键：回传 B站返回的 pagination_str 给下一页
        next_pagination = cursor.get("pagination_str")
        logger.info(
            f"[wbi main] page={page_idx} code={code} msg={msg!r} "
            f"top={len(top_replies)} replies={len(page_replies)} "
            f"all_count={all_count} is_end={is_end} next={next_num} "
            f"has_pagination_str={bool(next_pagination)}"
        )
        if code != 0:
            logger.warning(f"[wbi main] 接口返回非 0：code={code} msg={msg}")
            wbi_failed = True
            break
        if page_idx == 1:
            absorb(top_replies)
        added = absorb(page_replies)
        # 关键：如果当前页有 replies 但新增 0，说明 rpid 全部重复 → 游标没推进
        if page_replies and added == 0:
            logger.warning(
                f"[wbi main] 第 {page_idx} 页 {len(page_replies)} 条评论全部重复，"
                f"游标未推进，判定 wbi 接口游标失效，改走 legacy 接口"
            )
            wbi_failed = True
            break
        if is_end or not page_replies:
            break
        if next_pagination:
            pagination_str = next_pagination
        else:
            # 回退：B站没返回 pagination_str，用 next 数字兜底（可能无效，但避免死循环）
            next_val = int(next_num or 0)
            if next_val == 0:
                logger.info("[wbi main] 无 pagination_str 且 next=0，结束抓取")
                break
            pagination_str = json.dumps(
                {"offset": json.dumps({"type": 1, "direction": 1, "Data": {"cursor": next_val}}, separators=(",", ":"))},
                separators=(",", ":"),
            )
        time.sleep(0.4)

    legacy_failed = False

    def run_legacy(sort: int, label: str) -> int:
        nonlocal legacy_failed
        added_total = 0
        for page in range(1, pages + 1):
            try:
                data = _try_legacy_reply(aid, page, sort=sort)
            except Exception as exc:
                logger.warning(f"[legacy {label}] 第 {page} 页请求异常：{exc}")
                legacy_failed = True
                break
            code = data.get("code")
            msg = data.get("message")
            d = data.get("data") or {}
            page_items = d.get("replies") or []
            hots = d.get("hots") or []
            page_info = d.get("page") or {}
            logger.info(
                f"[legacy {label}] pn={page} code={code} msg={msg!r} "
                f"replies={len(page_items)} hots={len(hots)} page={page_info}"
            )
            if code != 0:
                logger.warning(f"[legacy {label}] 接口返回非 0：code={code} msg={msg}")
                legacy_failed = True
                break
            if page == 1 and sort == 2:
                added_total += absorb(hots)
            added_total += absorb(page_items)
            total = int(page_info.get("count") or 0)
            if not page_items:
                break
            if total and page * 20 >= total:
                break
            time.sleep(0.3)
        return added_total

    # ---- 2) 旧接口补充（wbi 失败或评论太少时） ----
    # wbi 游标失效（rpid 重复）或抓取量明显不足时，走 legacy /x/v2/reply 接口（pn 翻页明确）
    if wbi_failed or len(replies) < 30:
        logger.info(f"WBI 主接口结束（wbi_failed={wbi_failed}，{len(replies)} 条）；尝试旧 /x/v2/reply 补充。")
        run_legacy(sort=2, label="hot")
        if not legacy_failed:
            run_legacy(sort=0, label="time")

    # ---- 3) 新版 main 兜底 ----
    if (wbi_failed and legacy_failed) and len(replies) < 5:
        logger.info("旧接口与 wbi 都失败，尝试未签名的 /x/v2/reply/main 兜底。")
        next_cursor = 0
        for page_idx in range(1, pages + 1):
            try:
                data = _try_main_reply(aid, next_cursor)
            except Exception as exc:
                logger.warning(f"[main] 第 {page_idx} 页请求异常：{exc}")
                break
            code = data.get("code")
            d = data.get("data") or {}
            cursor = d.get("cursor") or {}
            page_replies = d.get("replies") or []
            is_end = bool(cursor.get("is_end"))
            next_cursor = int(cursor.get("next") or 0)
            logger.info(
                f"[main] page={page_idx} code={code} replies={len(page_replies)} "
                f"is_end={is_end} next={next_cursor}"
            )
            if code != 0:
                break
            absorb(page_replies)
            if is_end or not page_replies or next_cursor == 0:
                break
            time.sleep(0.4)

    logger.info(f"评论抓取完成：合计 {len(replies)} 条 (aid={aid})")
    return replies


# P2: 合并词集缓存（B站口语词表 + 学术词典），懒加载避免启动卡顿
_POS_SET: frozenset[str] | None = None
_NEG_SET: frozenset[str] | None = None
_RISK_SET: frozenset[str] | None = None
_CON_SET: frozenset[str] | None = None


def _positive_set() -> frozenset[str]:
    global _POS_SET
    if _POS_SET is None:
        s = set(POSITIVE_WORDS)
        if _LEXICON_OK:
            s |= _lex_positive()
        _POS_SET = frozenset(s)
    return _POS_SET


def _negative_set() -> frozenset[str]:
    global _NEG_SET
    if _NEG_SET is None:
        s = set(NEGATIVE_WORDS)
        if _LEXICON_OK:
            s |= _lex_negative()
        _NEG_SET = frozenset(s)
    return _NEG_SET


def _risk_set() -> frozenset[str]:
    global _RISK_SET
    if _RISK_SET is None:
        _RISK_SET = frozenset(RISK_WORDS)
    return _RISK_SET


def _con_set() -> frozenset[str]:
    global _CON_SET
    if _CON_SET is None:
        _CON_SET = frozenset(CONTROVERSY_WORDS)
    return _CON_SET


def _score_text_legacy(text: str) -> dict[str, Any]:
    """降级路径：原子串匹配（jieba 不可用时使用）。"""
    pos = sum(text.count(w) for w in POSITIVE_WORDS)
    neg = sum(text.count(w) for w in NEGATIVE_WORDS)
    risk = sum(text.count(w) for w in RISK_WORDS)
    con = sum(text.count(w) for w in CONTROVERSY_WORDS)
    if risk > 0:
        label = "risk"
    elif neg > pos and neg > 0:
        label = "neg"
    elif pos > neg and pos > 0:
        label = "pos"
    elif con > 0:
        label = "con"
    else:
        label = "neu"
    total = pos + neg
    return {
        "label": label, "pos": pos, "neg": neg, "risk": risk, "con": con,
        "score": pos - neg,
        "score_rel": round((pos - neg) / total, 3) if total > 0 else 0.0,
    }


def score_text(text: str) -> dict[str, Any]:
    """情感打分：jieba 分词 + 三库词典 + 否定词翻转 + 程度词加权。

    参考《文本分析》词典法：P-N 绝对分、(P-N)/(P+N) 相对分。
    - 否定词翻转后续情感词极性（"不"+"好"→负、"不"+"错"→正）
    - 程度词放大权重（"非常"x1.5、"极其"x2.0）
    - 分词后按词匹配，消除"牛顿"命中"牛"的子串误判
    jieba 不可用时降级为 _score_text_legacy 子串匹配。
    """
    if not _LEXICON_OK or not text:
        return _score_text_legacy(text)

    tokens = _lex_tokenize(text)
    pos = neg = 0.0
    risk = con = 0
    degree_buf = 1.0
    negate = False
    pset, nset = _positive_set(), _negative_set()
    rset, cset = _risk_set(), _con_set()
    denial = _lex_denial
    degree = _lex_degree()

    for tok in tokens:
        if tok in denial:
            negate = True
            continue
        deg = degree.get(tok)
        if deg is not None:
            degree_buf = deg
            continue
        if tok in rset:
            risk += 1
            continue
        if tok in cset:
            con += 1
            continue
        if tok in pset:
            # 否定翻转：否定+正向=负向；否定+负向=正向（"不错"=好）
            if negate:
                neg += degree_buf
            else:
                pos += degree_buf
            negate = False
            degree_buf = 1.0
        elif tok in nset:
            if negate:
                pos += degree_buf
            else:
                neg += degree_buf
            negate = False
            degree_buf = 1.0

    # label 判定：risk 占主导才算风险，否则按正负对比
    if risk > 0 and risk >= max(pos, neg):
        label = "risk"
    elif neg > pos and neg > 0:
        label = "neg"
    elif pos > neg and pos > 0:
        label = "pos"
    elif con > 0:
        label = "con"
    else:
        label = "neu"

    total = pos + neg
    return {
        "label": label,
        "pos": int(round(pos)), "neg": int(round(neg)),
        "risk": risk, "con": con,
        "score": round(pos - neg, 3),
        "score_rel": round((pos - neg) / total, 3) if total > 0 else 0.0,
    }


def dedupe_comments(replies: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """评论去重与水军过滤（P2 #10）：
    1. 同用户(mid)保留最高赞一条，去除重复发言
    2. 归一化文本相同且出现>=3次视为水军刷屏，每文本仅保留最高赞1条并打 spam_flag
    返回 (清洗后列表, 统计 {dup_by_user, spam_removed})
    """
    stats = {"dup_by_user": 0, "spam_removed": 0}
    # 1. 按 mid 去重（保留最高赞）
    keep_best: dict[str, dict[str, Any]] = {}
    for r in replies:
        mid = r.get("mid") or str(r.get("rpid", "")) or f"_anon_{id(r)}"
        cur = keep_best.get(mid)
        if cur is None or r.get("likes", 0) > cur.get("likes", 0):
            if cur is not None:
                stats["dup_by_user"] += 1
            keep_best[mid] = r
        else:
            stats["dup_by_user"] += 1
    uniq = list(keep_best.values())

    # 2. 重复文本水军过滤
    norm_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in uniq:
        norm = re.sub(r"[\s\W]+", "", r.get("text", "")).lower()
        norm_groups[norm].append(r)
    spam_ids: set[int] = set()
    for items in norm_groups.values():
        if len(items) >= 3:
            best = max(items, key=lambda x: x.get("likes", 0))
            best.setdefault("spam_flag", True)
            for it in items:
                if it is not best:
                    spam_ids.add(id(it))
                    stats["spam_removed"] += 1
    cleaned = [r for r in uniq if id(r) not in spam_ids]
    logger.info(f"去重水军过滤：原始 {len(replies)} → 去重 {len(uniq)} → 清洗 {len(cleaned)}（{stats}）")
    return cleaned, stats


def extract_keywords(comments: list[dict[str, Any]], topn: int = 12) -> list[str]:
    """关键词抽取：jieba 可用时用 TF-IDF（extract_tags），否则降级为词表计数。"""
    text = "\n".join(c["text"] for c in comments)
    if not text.strip():
        return []
    if _LEXICON_OK:
        return [w for w, _ in _lex_extract_tags(text, top_k=topn)]
    # 降级：词表子串计数
    candidates = set(POSITIVE_WORDS + NEGATIVE_WORDS + RISK_WORDS + CONTROVERSY_WORDS)
    for words in TOPIC_RULES.values():
        candidates.update(words)
    counts = Counter({w: text.count(w) for w in candidates if text.count(w) > 0})
    return [w for w, _ in counts.most_common(topn)]


def extract_keywords_weighted(comments: list[dict[str, Any]], topn: int = 12) -> list[dict[str, float]]:
    """带权重的关键词抽取，供前端展示词云/权重条。"""
    text = "\n".join(c["text"] for c in comments)
    if not text.strip() or not _LEXICON_OK:
        ks = extract_keywords(comments, topn)
        return [{"word": w, "weight": 1.0} for w in ks]
    return [{"word": w, "weight": round(s, 4)} for w, s in _lex_extract_tags(text, top_k=topn)]


def build_clusters(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """主题聚类：每条评论归入命中最多的单一话题（分词后匹配，消除子串误判）。
    原 build_clusters 取前2话题导致重复归桶，现改为最匹配单一话题。
    """
    topic_words = {topic: set(words) for topic, words in TOPIC_RULES.items()}
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for comment in comments:
        text = comment["text"]
        if _LEXICON_OK:
            toks = set(_lex_tokenize(text))
            hit_of = lambda words: sum(1 for w in words if w in toks)
        else:
            hit_of = lambda words: sum(1 for w in words if w in text)
        best_topic, best_hit = "其他讨论", 0
        for topic, words in topic_words.items():
            h = hit_of(words)
            if h > best_hit:
                best_hit, best_topic = h, topic
        buckets[best_topic].append(comment)

    clusters = []
    for topic, items in sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True)[:6]:
        labels = Counter(item["sentiment"] for item in items)
        sentiment = labels.most_common(1)[0][0] if labels else "neu"
        examples = [item["text"] for item in sorted(items, key=lambda x: x.get("likes", 0), reverse=True)[:2]]
        clusters.append({"topic": topic, "size": len(items), "sentiment": sentiment, "examples": examples})
    return clusters


# 风险等级阈值（可配置，参考舆情监测经验值；不同领域如游戏/美食/时政可调整）
RISK_THRESHOLDS: dict[str, dict[str, float]] = {
    "high": {"risk_rate": 0.08, "neg_rate": 0.45},
    "medium": {"risk_rate": 0.03, "neg_rate": 0.25, "con_rate": 0.18},
}


def risk_level(dist: dict[str, int], total: int) -> tuple[str, str]:
    if total == 0:
        return "unknown", "未获取到可分析评论，无法判断风险等级。"
    neg_rate = (dist.get("neg", 0) + dist.get("risk", 0)) / total
    risk_rate = dist.get("risk", 0) / total
    con_rate = dist.get("con", 0) / total
    th = RISK_THRESHOLDS
    if risk_rate >= th["high"]["risk_rate"] or neg_rate >= th["high"]["neg_rate"]:
        return "high", "负面或风险评论占比较高，建议重点关注评论区后续扩散。"
    if (risk_rate >= th["medium"]["risk_rate"]
            or neg_rate >= th["medium"]["neg_rate"]
            or con_rate >= th["medium"]["con_rate"]):
        return "medium", "存在一定争议或负面反馈，需要观察核心话题走向。"
    return "low", "公开评论整体风险较低，暂未看到明显集中负面爆发。"


def make_report(video: dict[str, Any], comments: list[dict[str, Any]], dist: dict[str, int],
                keywords: list[str], clusters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """生成舆情报告：优先 LLM（OpenAI 兼容，默认 DeepSeek），无 key 或失败时降级模板。

    通过环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 配置。
    """
    if _llm_generate_report is not None:
        return _llm_generate_report(video, comments, dist, keywords, clusters)
    # 模块不可用 → 纯模板
    return _template_report_fallback(video, comments, dist, keywords)


def _template_report_fallback(video: dict[str, Any], comments: list[dict[str, Any]],
                              dist: dict[str, int], keywords: list[str]) -> dict[str, Any]:
    """模板报告（LLM 不可用时的最终降级路径，与原 make_report 逻辑一致）。"""
    total = len(comments)
    title = video.get("title", "该视频")
    top_keywords = "、".join(keywords[:6]) if keywords else "暂无明显高频词"
    neg_items = [c["text"] for c in comments if c["sentiment"] in ("neg", "risk")][:4]
    pos_items = [c["text"] for c in comments if c["sentiment"] == "pos"][:4]

    if total == 0:
        return {
            "summary": f"已获取视频《{title}》的公开信息，但没有拿到可分析评论。",
            "positive": [],
            "negative": ["评论为空，可能是评论区关闭、接口限制、风控或当前分页无数据。"],
            "controversy": "暂无评论数据，不能判断争议点。",
            "suggestion": "建议换用浏览器已登录环境或减少请求频率后重试。",
            "ai_generated": False,
            "model": "template",
        }

    summary = (
        f"本次基于抓取到的 {total} 条公开评论做本地分析。"
        f"高频词集中在：{top_keywords}。"
        f"情绪分布中，正向 {dist.get('pos', 0)} 条、负向 {dist.get('neg', 0)} 条、风险 {dist.get('risk', 0)} 条。"
    )
    return {
        "summary": summary,
        "positive": pos_items or ["未识别到明显正向高赞评论。"],
        "negative": neg_items or ["未识别到明显负面或风险评论。"],
        "controversy": "争议主要由负面、风险和转折性表达共同决定；请结合下方典型评论复核语义，避免仅凭关键词误判。",
        "suggestion": "建议优先人工复核高赞负面评论和风险评论；如果用于正式汇报，可增加人工标注或接入更强的情感分类模型。",
        "ai_generated": False,
        "model": "template",
    }


# ---- 话题搜索（B站搜索 API） ----

def search_bilibili_videos(
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    order: str = "totalrank",
) -> dict[str, Any]:
    """调用 B站 WBI 签名搜索接口，按关键词搜索视频。

    参数：
        keyword: 搜索关键词
        page: 页码（从 1 开始）
        page_size: 每页结果数（默认 20，最大 50）
        order: 排序方式 totalrank/click/pubdate/dm/stow/scores

    返回：
        {
            "keyword": str,
            "page": int,
            "numResults": int,
            "numPages": int,
            "results": [
                {
                    "bvid", "aid", "title", "description", "arcurl", "pic",
                    "author", "mid", "play", "favorites", "like", "danmaku",
                    "tag", "typename", "duration", "pubdate", "review",
                }
            ]
        }
    """
    bootstrap_session()
    get_wbi_keys()

    raw_params = {
        "search_type": "video",
        "keyword": keyword,
        "page": page,
        "page_size": min(max(1, page_size), 50),
        "order": order,
        "highlight": 0,
    }
    signed = wbi_sign(raw_params)

    headers = dict(HEADERS)
    headers["Referer"] = "https://search.bilibili.com/"

    url = "https://api.bilibili.com/x/web-interface/wbi/search/type?" + urllib.parse.urlencode(signed)
    logger.info(f"搜索视频：keyword={keyword!r} page={page} order={order}")
    req = urllib.request.Request(url, headers=headers)
    with OPENER.open(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body)

    if data.get("code") != 0:
        raise RuntimeError(f"B站搜索接口异常：{data.get('message', data)}")

    d = data.get("data") or {}
    raw_results = d.get("result") or []

    results: list[dict[str, Any]] = []
    for item in raw_results:
        # 清理标题中的 <em> 高亮标签
        title = re.sub(r"</?em[^>]*>", "", item.get("title", ""))
        results.append({
            "bvid": item.get("bvid", ""),
            "aid": item.get("aid", 0),
            "title": title,
            "description": item.get("description", "").replace("\\n", " "),
            "arcurl": item.get("arcurl", ""),
            "pic": item.get("pic", ""),
            "author": item.get("author", ""),
            "mid": item.get("mid", 0),
            "play": item.get("play", 0),
            "favorites": item.get("favorites", 0),
            "like": item.get("like", 0),
            "danmaku": item.get("video_review", 0),
            "tag": item.get("tag", ""),
            "typename": item.get("typename", ""),
            "duration": item.get("duration", ""),
            "pubdate": item.get("pubdate", 0),
            "review": item.get("review", 0),
        })

    return {
        "keyword": keyword,
        "page": d.get("page", page),
        "numResults": d.get("numResults", len(results)),
        "numPages": d.get("numPages", 1),
        "results": results,
    }


def analyze_topic(
    keyword: str,
    top_n: int = 5,
    pages_per_video: int = 3,
) -> dict[str, Any]:
    """话题舆情分析：搜索关键词 → 取 top_n 热门视频 → 分别抓取评论 → 聚合分析。

    参数：
        keyword: 话题关键词
        top_n: 取搜索结果前 N 个视频（默认 5）
        pages_per_video: 每个视频抓取的评论页数（默认 3）

    返回：
        聚合分析结果，包含每个视频的独立分析和整体话题分析。
    """
    logger.info(f"开始话题分析：keyword={keyword!r} top_n={top_n} pages={pages_per_video}")

    # 1. 搜索视频
    search_result = search_bilibili_videos(keyword, page=1, page_size=top_n, order="click")
    videos = search_result["results"][:top_n]

    if not videos:
        raise ValueError(f"搜索「{keyword}」未找到相关视频，请换个关键词试试。")

    # 2. 逐视频抓取评论并分析
    all_comments: list[dict[str, Any]] = []
    video_analyses: list[dict[str, Any]] = []

    for idx, video in enumerate(videos):
        bvid = video["bvid"]
        logger.info(f"[话题] 分析视频 {idx + 1}/{len(videos)}：{video['title'][:30]}... ({bvid})")
        try:
            video_info = fetch_video_info(bvid)
            replies_raw = fetch_replies(int(video_info["aid"]), pages=pages_per_video)
            replies, dedupe_stats = dedupe_comments(replies_raw)

            for reply in replies:
                reply["sentiment"] = score_text(reply["text"])["label"]

            dist_counter = Counter(reply["sentiment"] for reply in replies)
            sentiments = {key: dist_counter.get(key, 0) for key in ["pos", "neu", "neg", "con", "risk"]}
            total = max(1, sum(sentiments.values()))
            sentiment_percent = {key: round(value * 100 / total, 1) for key, value in sentiments.items()}
            risk, reason = risk_level(sentiments, len(replies))
            keywords = extract_keywords(replies, topn=8)
            hot_comments = sorted(replies, key=lambda x: x.get("likes", 0), reverse=True)[:10]

            stat = video_info.get("stat") or {}
            owner = video_info.get("owner") or {}

            public_comment_count = int(stat.get("reply", 0) or 0)
            video_analysis = {
                "bvid": bvid,
                "title": video_info.get("title"),
                "author": owner.get("name"),
                "pic": video_info.get("pic"),
                "arcurl": video["arcurl"],
                "views": stat.get("view", 0),
                "likes": stat.get("like", 0),
                "coins": stat.get("coin", 0),
                "favorites": stat.get("favorite", 0),
                "danmaku": stat.get("danmaku", 0),
                "replyCountFromVideo": public_comment_count,
                "publicCommentCount": public_comment_count,
                "commentCount": len(replies),
                "needsLogin": len(replies) <= 3 and public_comment_count > 15,
                "risk": risk,
                "riskReason": reason,
                "sentiments": sentiment_percent,
                "sentimentCounts": sentiments,
                "keywords": keywords,
                "hotComments": hot_comments,
            }
            video_analyses.append(video_analysis)
            all_comments.extend(replies)
            logger.info(f"[话题] 视频 {idx + 1} 完成：{len(replies)} 条评论, 风险={risk}")

        except Exception as exc:
            logger.warning(f"[话题] 视频 {idx + 1} 分析失败：{exc}")
            video_analyses.append({
                "bvid": bvid,
                "title": video["title"],
                "author": video["author"],
                "pic": video["pic"],
                "arcurl": video["arcurl"],
                "error": str(exc),
                "commentCount": 0,
            })

    # 3. 聚合分析
    for comment in all_comments:
        if "sentiment" not in comment:
            comment["sentiment"] = score_text(comment["text"])["label"]

    agg_counter = Counter(c["sentiment"] for c in all_comments)
    agg_sentiments = {key: agg_counter.get(key, 0) for key in ["pos", "neu", "neg", "con", "risk"]}
    agg_total = max(1, sum(agg_sentiments.values()))
    agg_sentiment_percent = {key: round(v * 100 / agg_total, 1) for key, v in agg_sentiments.items()}
    agg_risk, agg_reason = risk_level(agg_sentiments, len(all_comments))
    agg_keywords = extract_keywords(all_comments, topn=15)
    agg_keywords_weighted = extract_keywords_weighted(all_comments, topn=15)
    agg_clusters = build_clusters(all_comments)
    negative_timeline = _build_negative_timeline(all_comments)

    # LLM 增强情感分析
    llm_sentiment_stats = {"total_neutral": 0, "enhanced": 0, "unchanged": 0}
    if _LLM_SENTIMENT_OK and enhance_neutral_comments is not None:
        try:
            llm_sentiment_stats = enhance_neutral_comments(all_comments)
        except Exception as exc:
            logger.warning(f"[话题] LLM 情感增强失败：{exc}")

    # 重新统计 LLM 增强后的情感分布
    if llm_sentiment_stats["enhanced"] > 0:
        agg_counter = Counter(c["sentiment"] for c in all_comments)
        agg_sentiments = {key: agg_counter.get(key, 0) for key in ["pos", "neu", "neg", "con", "risk"]}
        agg_total = max(1, sum(agg_sentiments.values()))
        agg_sentiment_percent = {key: round(v * 100 / agg_total, 1) for key, v in agg_sentiments.items()}
        agg_risk, agg_reason = risk_level(agg_sentiments, len(all_comments))

    # 话题整体报告
    topic_report = _make_topic_report(keyword, video_analyses, all_comments, agg_sentiments, agg_keywords)

    result = {
        "type": "topic",
        "platform": "B站",
        "keyword": keyword,
        "searchTotal": search_result["numResults"],
        "requestedCount": min(top_n, len(videos)),
        "analyzedCount": len(video_analyses),
        "totalComments": len(all_comments),
        "videos": video_analyses,
        "risk": agg_risk,
        "riskReason": agg_reason,
        "sentiments": agg_sentiment_percent,
        "sentimentCounts": agg_sentiments,
        "keywords": agg_keywords,
        "keywordsWeighted": agg_keywords_weighted,
        "clusters": agg_clusters,
        "negativeTimeline": negative_timeline,
        "comments": sorted(all_comments, key=lambda x: x.get("likes", 0), reverse=True)[:50],
        "report": topic_report,
        "llmSentimentEnhanced": _LLM_SENTIMENT_OK,
        "llmSentimentStats": llm_sentiment_stats,
        "fetchedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return _enrich_topic_meta(result)


def _neg_ratio(sentiments: dict[str, Any]) -> float:
    """负面占比口径：负面 + 风险（与 risk_level 一致）。sentiments 为百分比 dict。"""
    if not sentiments:
        return 0.0
    return round(float(sentiments.get("neg", 0) or 0) + float(sentiments.get("risk", 0) or 0), 1)


def _pick_compare_words(platform_data: dict[str, Any], limit: int = 6) -> list[str]:
    words: list[str] = []
    for item in (platform_data.get("keywordsWeighted") or []):
        word = item.get("word") if isinstance(item, dict) else item
        word = str(word or "").strip()
        if len(word) >= 2 and word not in words:
            words.append(word)
    for word in (platform_data.get("keywords") or []):
        word = str(word or "").strip()
        if len(word) >= 2 and word not in words:
            words.append(word)
    return words[:limit]


def _pick_compare_topics(platform_data: dict[str, Any], limit: int = 4, risky_only: bool = False) -> list[str]:
    topics: list[str] = []
    risky_labels = {"neg", "risk", "con"}
    for cluster in (platform_data.get("clusters") or []):
        if not isinstance(cluster, dict):
            continue
        if risky_only and cluster.get("sentiment") not in risky_labels:
            continue
        topic = str(cluster.get("topic") or "").strip()
        if not topic or topic == "其他讨论" or topic in topics:
            continue
        topics.append(topic)
        if len(topics) >= limit:
            break
    return topics


def _describe_platform_tone(platform_label: str, platform_data: dict[str, Any]) -> dict[str, Any]:
    sentiments = platform_data.get("sentiments") or {}
    pos = float(sentiments.get("pos", 0) or 0)
    neu = float(sentiments.get("neu", 0) or 0)
    con = float(sentiments.get("con", 0) or 0)
    risk = float(sentiments.get("risk", 0) or 0)
    neg_ratio = _neg_ratio(sentiments)
    topics = _pick_compare_topics(platform_data, limit=2)
    words = _pick_compare_words(platform_data, limit=4)

    if neg_ratio >= 35 or risk >= 8 or con >= 18:
        tone = "争议密集"
        summary = f"{platform_label}侧负面/风险合计 {neg_ratio}% ，讨论更容易围绕争议点继续发酵。"
    elif pos >= 45 and neg_ratio <= 18:
        tone = "种草导向"
        summary = f"{platform_label}侧正面表达占优，更偏体验分享、推荐与安利。"
    elif neu >= 40 and neg_ratio < 25:
        tone = "理性讨论"
        summary = f"{platform_label}侧中性信息占比更高，用户更偏分析、比较与判断。"
    else:
        tone = "情绪表达"
        summary = f"{platform_label}侧情绪表达更直接，评论区更容易出现态度化发言。"

    if topics:
        summary += f" 话题集中在「{'」「'.join(topics)}」。"
    elif words:
        summary += f" 高频词集中在「{'」「'.join(words[:3])}」。"

    return {
        "tone": tone,
        "summary": summary,
        "topics": topics,
        "keywords": words,
    }


def _build_compare_diff(bili: dict[str, Any] | None, xhs: dict[str, Any] | None) -> dict[str, Any]:
    """计算两平台对比差异，并输出可直接展示的结构化解释。"""
    diff: dict[str, Any] = {
        "bothOk": bool(bili and xhs),
    }
    if not (bili and xhs):
        return diff

    sent_order = ["pos", "neu", "neg", "con", "risk"]
    b_sent = bili.get("sentiments", {}) or {}
    x_sent = xhs.get("sentiments", {}) or {}
    diff["sentimentDelta"] = {k: round(float(b_sent.get(k, 0) or 0) - float(x_sent.get(k, 0) or 0), 1) for k in sent_order}

    b_neg = _neg_ratio(b_sent)
    x_neg = _neg_ratio(x_sent)
    diff["biliNegRatio"] = b_neg
    diff["xhsNegRatio"] = x_neg
    diff["negRatioDiff"] = round(abs(b_neg - x_neg), 1)
    if b_neg > x_neg:
        diff["moreNegativePlatform"] = "bilibili"
    elif x_neg > b_neg:
        diff["moreNegativePlatform"] = "xiaohongshu"
    else:
        diff["moreNegativePlatform"] = "equal"

    b_pos = round(float(b_sent.get("pos", 0) or 0), 1)
    x_pos = round(float(x_sent.get("pos", 0) or 0), 1)
    diff["biliPosRatio"] = b_pos
    diff["xhsPosRatio"] = x_pos
    diff["posRatioDiff"] = round(abs(b_pos - x_pos), 1)
    if b_pos > x_pos:
        diff["morePositivePlatform"] = "bilibili"
    elif x_pos > b_pos:
        diff["morePositivePlatform"] = "xiaohongshu"
    else:
        diff["morePositivePlatform"] = "equal"

    b_con = round(float(b_sent.get("con", 0) or 0) + float(b_sent.get("risk", 0) or 0), 1)
    x_con = round(float(x_sent.get("con", 0) or 0) + float(x_sent.get("risk", 0) or 0), 1)
    diff["biliControversyRatio"] = b_con
    diff["xhsControversyRatio"] = x_con
    diff["controversyDiff"] = round(abs(b_con - x_con), 1)
    if b_con > x_con:
        diff["moreControversialPlatform"] = "bilibili"
    elif x_con > b_con:
        diff["moreControversialPlatform"] = "xiaohongshu"
    else:
        diff["moreControversialPlatform"] = "equal"

    b_kws = _pick_compare_words(bili, limit=12)
    x_kws = _pick_compare_words(xhs, limit=12)
    b_set, x_set = set(b_kws), set(x_kws)
    diff["commonKeywords"] = [k for k in b_kws if k in x_set][:12]
    diff["biliOnlyKeywords"] = [k for k in b_kws if k not in x_set][:12]
    diff["xhsOnlyKeywords"] = [k for k in x_kws if k not in b_set][:12]

    b_topics = _pick_compare_topics(bili, limit=6)
    x_topics = _pick_compare_topics(xhs, limit=6)
    b_topic_set, x_topic_set = set(b_topics), set(x_topics)
    diff["commonTopics"] = [topic for topic in b_topics if topic in x_topic_set][:6]
    diff["biliOnlyTopics"] = [topic for topic in b_topics if topic not in x_topic_set][:6]
    diff["xhsOnlyTopics"] = [topic for topic in x_topics if topic not in b_topic_set][:6]

    diff["biliRisk"] = bili.get("risk", "unknown")
    diff["xhsRisk"] = xhs.get("risk", "unknown")

    bili_tone = _describe_platform_tone("B站", bili)
    xhs_tone = _describe_platform_tone("小红书", xhs)
    diff["biliTone"] = bili_tone
    diff["xhsTone"] = xhs_tone

    shared_focus = diff["commonTopics"] or diff["commonKeywords"][:5]
    bili_focus = diff["biliOnlyTopics"] or diff["biliOnlyKeywords"][:4]
    xhs_focus = diff["xhsOnlyTopics"] or diff["xhsOnlyKeywords"][:4]
    bili_risky_topics = _pick_compare_topics(bili, limit=3, risky_only=True)
    xhs_risky_topics = _pick_compare_topics(xhs, limit=3, risky_only=True)

    why: list[str] = []
    actions: list[str] = []
    if diff["moreNegativePlatform"] == "bilibili" and diff["negRatioDiff"] >= 5:
        driver = bili_risky_topics[0] if bili_risky_topics else (bili_focus[0] if bili_focus else "平台独有讨论")
        headline = f"B站更偏负面，主要由「{driver}」一类讨论把风险拉高。"
        why.append(f"B站负面+风险占比 {b_neg}% ，比小红书高 {diff['negRatioDiff']} 个百分点。")
        if bili_risky_topics:
            why.append(f"B站的负面主要集中在「{'」「'.join(bili_risky_topics[:3])}」这几类话题。")
        if bili_focus:
            why.append(f"B站独有关注点偏向「{'」「'.join(bili_focus[:3])}」，说明争议更集中在这些点上。")
        actions.append(f"优先复核 B站里与「{driver}」相关的高赞评论，判断是否已进入持续发酵。")
    elif diff["moreNegativePlatform"] == "xiaohongshu" and diff["negRatioDiff"] >= 5:
        driver = xhs_risky_topics[0] if xhs_risky_topics else (xhs_focus[0] if xhs_focus else "平台独有讨论")
        headline = f"小红书更偏负面，主要由「{driver}」一类讨论把风险拉高。"
        why.append(f"小红书负面+风险占比 {x_neg}% ，比 B站高 {diff['negRatioDiff']} 个百分点。")
        if xhs_risky_topics:
            why.append(f"小红书的负面主要集中在「{'」「'.join(xhs_risky_topics[:3])}」这几类话题。")
        if xhs_focus:
            why.append(f"小红书独有关注点偏向「{'」「'.join(xhs_focus[:3])}」，说明情绪更容易围绕这些点扩散。")
        actions.append(f"优先复核小红书里与「{driver}」相关的高赞评论，确认是否需要先做回应或澄清。")
    else:
        headline = "双平台整体情绪接近，差异更多体现在表达方式和关注点。"
        why.append(f"两平台负面+风险占比差仅 {diff['negRatioDiff']} 个百分点，整体态度没有明显断层。")
        if shared_focus:
            why.append(f"双方都在讨论「{'」「'.join(shared_focus[:4])}」，说明主议题是一致的。")
        if bili_focus or xhs_focus:
            why.append(
                f"真正的分化来自平台独有焦点：B站更关注「{'」「'.join(bili_focus[:2]) if bili_focus else '暂无'}」，"
                f"小红书更关注「{'」「'.join(xhs_focus[:2]) if xhs_focus else '暂无'}」。"
            )
        actions.append("先看双方共同热议点，再分别抽查平台独有关注点，能更快判断差异是议题差还是表达差。")

    if diff["controversyDiff"] >= 6:
        higher = "B站" if diff["moreControversialPlatform"] == "bilibili" else "小红书"
        why.append(f"{higher} 的争议/风险表达更集中，说明该平台更容易把讨论推向对立或预警状态。")

    if bili_tone["tone"] != xhs_tone["tone"]:
        why.append(f"平台气质也不同：B站更像“{bili_tone['tone']}”，小红书更像“{xhs_tone['tone']}”。")

    if shared_focus:
        actions.append(f"共同热议点先盯「{'」「'.join(shared_focus[:3])}」，这是跨平台都在放大的主线。")
    if diff["morePositivePlatform"] != "equal" and diff["posRatioDiff"] >= 5:
        better = "B站" if diff["morePositivePlatform"] == "bilibili" else "小红书"
        actions.append(f"{better} 的正向承接更强，可把该平台当成观察用户接受度和正反馈的参考面。")

    diff["explanation"] = {
        "headline": headline,
        "why": why[:5],
        "sharedFocus": shared_focus[:6],
        "divergentFocus": {
            "bilibili": bili_focus[:4],
            "xiaohongshu": xhs_focus[:4],
        },
        "actions": actions[:4],
    }

    insights = [headline]
    insights.extend(why[:3])
    if shared_focus:
        insights.append(f"共同热议：{'、'.join(shared_focus[:4])}。")
    if bili_focus or xhs_focus:
        insights.append(
            f"平台分化点：B站看「{'、'.join(bili_focus[:3]) if bili_focus else '暂无'}」，"
            f"小红书看「{'、'.join(xhs_focus[:3]) if xhs_focus else '暂无'}」。"
        )
    diff["insights"] = insights[:6]
    return diff


def analyze_topic_compare(keyword: str, top_n: int = 5, pages: int = 3) -> dict[str, Any]:
    """双平台对比分析：同时拉取 B站 + 小红书同一话题，并排对比情绪/关键词/风险差异。

    两个平台并行分析，任一平台失败不影响另一平台，失败信息记录在对应平台的 error 字段。
    """
    from concurrent.futures import ThreadPoolExecutor

    results: dict[str, Any] = {"bilibili": None, "xiaohongshu": None}
    errors: dict[str, str] = {}

    def _run_bili():
        try:
            results["bilibili"] = analyze_topic(keyword, top_n=top_n, pages_per_video=pages)
        except Exception as exc:
            errors["bilibili"] = str(exc)
            logger.warning(f"对比分析-B站失败：{exc}")

    def _run_xhs():
        try:
            results["xiaohongshu"] = analyze_xhs_topic(keyword, top_n=top_n, pages_per_note=pages)
        except Exception as exc:
            errors["xiaohongshu"] = str(exc)
            logger.warning(f"对比分析-小红书失败：{exc}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_run_bili)
        f2 = pool.submit(_run_xhs)
        f1.result()
        f2.result()

    bili = results["bilibili"]
    xhs = results["xiaohongshu"]
    if bili is None and xhs is None:
        raise RuntimeError(
            f"两个平台均分析失败。B站：{errors.get('bilibili', '未知')}；小红书：{errors.get('xiaohongshu', '未知')}"
        )

    result = {
        "type": "compare",
        "keyword": keyword,
        "bilibili": bili,
        "xiaohongshu": xhs,
        "errors": errors,
        "diff": _build_compare_diff(bili, xhs),
        "fetchedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return _enrich_compare_meta(result)


def _make_topic_report(
    keyword: str,
    video_analyses: list[dict[str, Any]],
    all_comments: list[dict[str, Any]],
    sentiments: dict[str, int],
    keywords: list[str],
) -> str:
    """生成话题分析的文本报告。"""
    total = sum(sentiments.values())
    pos_pct = round(sentiments.get("pos", 0) * 100 / max(1, total), 1)
    neg_pct = round(sentiments.get("neg", 0) * 100 / max(1, total), 1)
    risk_pct = round(sentiments.get("risk", 0) * 100 / max(1, total), 1)

    lines = [
        f"## 话题舆情报告：{keyword}",
        "",
        f"**分析范围**：{len(video_analyses)} 个相关视频，共 {total} 条评论",
        "",
        "### 整体情感分布",
        f"- 正面 {pos_pct}% | 负面 {neg_pct}% | 风险 {risk_pct}%",
        "",
        "### 热门关键词",
        f"{'、'.join(keywords[:10]) if keywords else '暂无'}",
        "",
        "### 各视频分析",
    ]

    for i, va in enumerate(video_analyses):
        if va.get("error"):
            lines.append(f"{i + 1}. **{va.get('title', '未知')}** — 分析失败：{va['error']}")
            continue
        vs = va.get("sentimentCounts", {})
        vt = max(1, sum(vs.values()))
        v_pos = round(vs.get("pos", 0) * 100 / vt, 1)
        v_neg = round(vs.get("neg", 0) * 100 / vt, 1)
        v_risk = round(vs.get("risk", 0) * 100 / vt, 1)
        lines.append(
            f"{i + 1}. **{va.get('title', '未知')}**（{va.get('author', '')}）"
            f" — 播放 {va.get('views', 0)} | 评论 {va.get('commentCount', 0)}"
            f" | 正面 {v_pos}% 负面 {v_neg}% 风险 {v_risk}%"
        )

    return "\n".join(lines)


def analyze_xhs_topic(keyword: str, top_n: int = 5, pages_per_note: int = 3) -> dict[str, Any]:
    """小红书话题聚合分析：搜索笔记 → 抓取评论 → 聚合分析。"""
    logger.info(f"开始小红书话题分析：keyword={keyword} top_n={top_n} pages={pages_per_note}")
    
    # 搜索笔记
    search_result = xhs_client.search_notes(keyword, page=1, page_size=top_n)
    notes = search_result.get("results", [])
    
    if not notes:
        raise RuntimeError(f"搜索不到相关笔记：{keyword}")
    
    all_comments = []
    video_results = []
    xhs_cookies = xhs_client.load_xhs_cookies() if xhs_client else {}
    playwright_available = False
    try:
        from analysis.xhs_login import _sign  # noqa: F401
        playwright_available = True
    except Exception:
        playwright_available = False
    
    for i, note in enumerate(notes[:top_n]):
        note_id = note["id"]
        xsec_token = note.get("xsecToken", "")
        title = note.get("title", f"笔记 {i+1}")
        
        logger.info(f"[{i+1}/{min(top_n, len(notes))}] 分析笔记: {title[:30]}")
        
        try:
            # 获取笔记详情（用于提取评论）
            ni = xhs_client.fetch_note_info(note_id, xsec_token)
            # 获取评论
            comments = xhs_client.fetch_comments(note_id, xsec_token, max_pages=pages_per_note, note_info=ni)
            
            # 情感标注
            for c in comments:
                c["sentiment"] = score_text(c["text"])["label"]
            
            # 单笔记统计
            dist = Counter(c["sentiment"] for c in comments)
            total = max(1, sum(dist.values()))
            sent_pct = {k: round(dist.get(k, 0) * 100 / total, 1) for k in ["pos", "neu", "neg", "con", "risk"]}
            
            interact_info = ni.get("interactInfo") or {}
            public_comment_count = int(interact_info.get("commentCount", 0) or 0)
            needs_login = len(comments) == 0 or (len(comments) <= 5 and public_comment_count > 15)
            login_hint_parts = []
            if needs_login:
                if not xhs_cookies.get("a1"):
                    login_hint_parts.append("Cookie 未配置（缺少 a1/web_session），建议先登录小红书。")
                elif not playwright_available:
                    login_hint_parts.append("Playwright 签名依赖未安装，建议执行 playwright install chromium 后重试。")
                else:
                    login_hint_parts.append("Cookie 可能已过期，建议重新登录小红书。")
            video_results.append({
                "noteId": note_id,
                "title": title,
                "author": note.get("user", {}).get("nickname", ""),
                "platform": "小红书",
                "pic": (ni.get("imageList") or [{}])[0].get("url", "") if ni.get("imageList") else "",
                "noteUrl": f"https://www.xiaohongshu.com/explore/{note_id}",
                "commentCount": len(comments),
                "replyCountFromNote": public_comment_count,
                "publicCommentCount": public_comment_count,
                "needsLogin": needs_login,
                "playwrightMissing": not playwright_available,
                "loginHint": "".join(login_hint_parts),
                "sentiments": sent_pct,
                "sentimentCounts": dict(dist),
                "risk": risk_level(sent_pct, len(comments))[0],
            })
            
            all_comments.extend(comments)
            
        except Exception as exc:
            logger.warning(f"笔记分析失败: {title[:30]} - {exc}")
            video_results.append({
                "noteId": note_id,
                "title": title,
                "author": note.get("user", {}).get("nickname", ""),
                "platform": "小红书",
                "noteUrl": f"https://www.xiaohongshu.com/explore/{note_id}",
                "commentCount": 0,
                "error": str(exc),
            })
    
    # 聚合分析
    for c in all_comments:
        if "sentiment" not in c:
            c["sentiment"] = score_text(c["text"])["label"]
    
    dist_counter = Counter(c["sentiment"] for c in all_comments)
    sentiments = {k: dist_counter.get(k, 0) for k in ["pos", "neu", "neg", "con", "risk"]}
    total = max(1, sum(sentiments.values()))
    sentiment_percent = {k: round(v * 100 / total, 1) for k, v in sentiments.items()}
    risk, reason = risk_level(sentiments, len(all_comments))
    keywords = extract_keywords(all_comments)
    keywords_weighted = extract_keywords_weighted(all_comments)
    clusters = build_clusters(all_comments)
    negative_timeline = _build_negative_timeline(all_comments)
    hot_comments = sorted(all_comments, key=lambda x: x.get("likes", 0), reverse=True)[:50]
    
    report = _make_xhs_topic_report(keyword, video_results, sentiments, keywords, clusters)
    
    result = {
        "type": "xhs_topic",
        "platform": "小红书",
        "keyword": keyword,
        "searchTotal": search_result.get("total", 0),
        "requestedCount": min(top_n, len(notes)),
        "analyzedCount": len(video_results),
        "totalComments": len(all_comments),
        "playwrightMissing": not playwright_available,
        "videos": video_results,
        "risk": risk,
        "riskReason": reason,
        "sentiments": sentiment_percent,
        "sentimentCounts": sentiments,
        "keywords": keywords,
        "keywordsWeighted": keywords_weighted,
        "clusters": clusters,
        "negativeTimeline": negative_timeline,
        "comments": hot_comments,
        "report": report,
        "fetchedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return _enrich_topic_meta(result)


def _make_xhs_topic_report(keyword, videos, sentiments, keywords, clusters):
    """生成小红书话题分析文本报告。"""
    lines = [f"# 小红书话题舆情报告：{keyword}\n"]
    lines.append(f"## 概览\n")
    lines.append(f"- 分析笔记数：{len(videos)}")
    total_c = sum(v.get("commentCount", 0) for v in videos)
    lines.append(f"- 总评论数：{total_c}")
    lines.append(f"- 正面 {sentiments.get('pos', 0):.1f}% / 中性 {sentiments.get('neu', 0):.1f}% / 负面 {sentiments.get('neg', 0):.1f}%")
    lines.append("")
    
    for v in videos:
        lines.append(f"### {v.get('title', '未知')}")
        lines.append(f"- 作者：{v.get('author', '未知')} | 评论数：{v.get('commentCount', 0)}")
        s = v.get("sentiments", {})
        lines.append(f"- 情感：正面 {s.get('pos', 0):.1f}% / 中性 {s.get('neu', 0):.1f}% / 负面 {s.get('neg', 0):.1f}%")
        if v.get("error"):
            lines.append(f"- ⚠️ 分析失败：{v['error']}")
        lines.append("")
    
    if keywords:
        lines.append("## 热门关键词\n" + "、".join(keywords[:20]))
    
    if clusters:
        lines.append("\n## 观点聚类")
        for cl in clusters[:8]:
            lines.append(f"- **{cl.get('topic', '')}**（{cl.get('size', 0)} 条，{cl.get('sentiment', '')}）")
    
    return "\n".join(lines)


def _resolve_public_comment_count(result: dict[str, Any]) -> int:
    for key in ("publicCommentCount", "replyCountFromVideo", "replyCountFromNote"):
        value = result.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def _calc_coverage_rate(result: dict[str, Any]) -> float | None:
    public_count = _resolve_public_comment_count(result)
    comment_count = int(result.get("commentCount", 0) or 0)
    if public_count <= 0:
        return 100.0 if comment_count > 0 else None
    return round(min(100.0, comment_count * 100.0 / public_count), 1)


def _parse_comment_ts(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = int(value)
        if ts > 10**12:
            ts //= 1000
        return ts if ts > 0 else None

    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{10,13}", text):
        ts = int(text)
        if ts > 10**12:
            ts //= 1000
        return ts if ts > 0 else None

    normalized = text.replace("/", "-").replace("T", " ").replace("Z", "").strip()
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(normalized, fmt).timestamp())
        except ValueError:
            continue
    return None


def _pick_timeline_bucket(span_seconds: int) -> tuple[int, str, str]:
    if span_seconds <= 6 * 3600:
        return 1800, "%m-%d %H:%M", "30分钟"
    if span_seconds <= 24 * 3600:
        return 7200, "%m-%d %H:%M", "2小时"
    if span_seconds <= 3 * 24 * 3600:
        return 6 * 3600, "%m-%d %H:%M", "6小时"
    if span_seconds <= 14 * 24 * 3600:
        return 24 * 3600, "%m-%d", "天"
    if span_seconds <= 90 * 24 * 3600:
        return 7 * 24 * 3600, "%m-%d", "周"
    return 30 * 24 * 3600, "%Y-%m", "月"


def _describe_timeline_stage(negative_ratio: float, negative_count: int, risk_count: int) -> str:
    if negative_count <= 0 and risk_count <= 0:
        return "平稳"
    if negative_ratio >= 45 or risk_count >= 3 or negative_count >= 8:
        return "爆发"
    if negative_ratio >= 28 or risk_count >= 1 or negative_count >= 4:
        return "升温"
    return "露头"


def _timeline_terms(comments: list[dict[str, Any]], topn: int = 3) -> list[str]:
    if not comments:
        return []
    weighted = extract_keywords_weighted(comments, topn=topn)
    terms = [str(item.get("word") or "").strip() for item in weighted if isinstance(item, dict)]
    if terms:
        return [term for term in terms if term][:topn]
    plain = extract_keywords(comments, topn=topn)
    return [str(term).strip() for term in plain if str(term).strip()][:topn]


def _build_negative_timeline(comments: list[dict[str, Any]]) -> dict[str, Any] | None:
    timed_comments: list[dict[str, Any]] = []
    for comment in comments or []:
        ts = _parse_comment_ts(comment.get("time"))
        if ts is None:
            continue
        timed_comments.append({"ts": ts, "comment": comment})

    if len(timed_comments) < 3:
        return None

    timed_comments.sort(key=lambda item: item["ts"])
    span_seconds = max(0, timed_comments[-1]["ts"] - timed_comments[0]["ts"])
    bucket_seconds, label_fmt, bucket_unit = _pick_timeline_bucket(span_seconds)
    anchor = timed_comments[0]["ts"]
    buckets: dict[int, dict[str, Any]] = {}

    for entry in timed_comments:
        ts = entry["ts"]
        idx = 0 if bucket_seconds <= 0 else int((ts - anchor) // bucket_seconds)
        bucket_ts = anchor + idx * bucket_seconds
        bucket = buckets.setdefault(bucket_ts, {
            "startTs": bucket_ts,
            "items": [],
            "negativeItems": [],
            "controversyItems": [],
            "totalCount": 0,
            "negativeCount": 0,
            "riskCount": 0,
            "controversyCount": 0,
        })
        comment = entry["comment"]
        sentiment = str(comment.get("sentiment") or "")
        bucket["items"].append(comment)
        bucket["totalCount"] += 1
        if sentiment in ("neg", "risk"):
            bucket["negativeCount"] += 1
            bucket["negativeItems"].append(comment)
        if sentiment == "risk":
            bucket["riskCount"] += 1
        if sentiment in ("neg", "risk", "con"):
            bucket["controversyCount"] += 1
            bucket["controversyItems"].append(comment)

    points: list[dict[str, Any]] = []
    for bucket_ts in sorted(buckets):
        bucket = buckets[bucket_ts]
        total_count = bucket["totalCount"]
        negative_ratio = round(bucket["negativeCount"] * 100 / max(1, total_count), 1)
        risk_ratio = round(bucket["riskCount"] * 100 / max(1, total_count), 1)
        controversy_terms = _timeline_terms(bucket["controversyItems"], topn=3)
        points.append({
            "ts": bucket_ts,
            "label": datetime.fromtimestamp(bucket_ts).strftime(label_fmt),
            "totalCount": total_count,
            "negativeCount": bucket["negativeCount"],
            "negativeRatio": negative_ratio,
            "riskCount": bucket["riskCount"],
            "riskRatio": risk_ratio,
            "controversyCount": bucket["controversyCount"],
            "stage": _describe_timeline_stage(negative_ratio, bucket["negativeCount"], bucket["riskCount"]),
            "keywords": controversy_terms,
        })

    if not points:
        return None

    negative_points = [point for point in points if point["negativeCount"] > 0]
    controversy_comments = [entry["comment"] for entry in timed_comments if str(entry["comment"].get("sentiment") or "") in ("neg", "risk", "con")]
    overall_terms = _timeline_terms(controversy_comments, topn=6)
    spark_point = negative_points[0] if negative_points else points[0]
    peak_point = max(negative_points or points, key=lambda point: (point["negativeRatio"], point["negativeCount"], point["riskCount"], point["totalCount"]))
    latest_point = points[-1]

    milestones: list[dict[str, Any]] = []
    if spark_point["negativeCount"] > 0:
        milestones.append({
            "type": "spark",
            "title": "首次露头",
            "label": spark_point["label"],
            "desc": f"这一时段开始出现可见负面讨论，负面/风险占比达到 {spark_point['negativeRatio']}%。",
            "keywords": spark_point.get("keywords") or overall_terms[:2],
            "stage": spark_point["stage"],
        })

    peak_title = "负面爆发峰值" if peak_point["stage"] == "爆发" else "负面升温拐点"
    peak_desc = (
        f"峰值时段共抓到 {peak_point['totalCount']} 条评论，"
        f"其中负面/风险占比 {peak_point['negativeRatio']}%，风险评论 {peak_point['riskCount']} 条。"
    )
    milestones.append({
        "type": "peak",
        "title": peak_title,
        "label": peak_point["label"],
        "desc": peak_desc,
        "keywords": peak_point.get("keywords") or overall_terms[:3],
        "stage": peak_point["stage"],
    })

    if latest_point["label"] != peak_point["label"]:
        latest_gap = peak_point["negativeRatio"] - latest_point["negativeRatio"]
        latest_title = "当前仍在高压区" if latest_gap <= 8 else "当前进入回落观察"
        latest_desc = (
            f"最近时段负面/风险占比为 {latest_point['negativeRatio']}%，"
            f"{'仍接近峰值，需持续关注。' if latest_gap <= 8 else f'较峰值回落 {round(latest_gap, 1)} 个百分点。'}"
        )
        milestones.append({
            "type": "latest",
            "title": latest_title,
            "label": latest_point["label"],
            "desc": latest_desc,
            "keywords": latest_point.get("keywords") or overall_terms[:2],
            "stage": latest_point["stage"],
        })

    if peak_point["negativeRatio"] >= 45:
        summary = f"负面讨论出现明显爆发，峰值在 {peak_point['label']}，负面/风险占比达到 {peak_point['negativeRatio']}%。"
    elif latest_point["negativeRatio"] > spark_point["negativeRatio"] + 10:
        summary = f"负面情绪仍在抬升，最近时段比首次露头高出 {round(latest_point['negativeRatio'] - spark_point['negativeRatio'], 1)} 个百分点。"
    elif latest_point["negativeRatio"] + 8 < peak_point["negativeRatio"]:
        summary = f"负面声量已较峰值回落，但峰值阶段的争议点仍值得复核。"
    else:
        summary = "负面讨论呈阶段性波动，建议结合关键节点和高频争议词做复核。"

    return {
        "summary": summary,
        "bucketUnit": bucket_unit,
        "windowLabel": f"{points[0]['label']} → {points[-1]['label']}",
        "totalTimedComments": len(timed_comments),
        "peak": {
            "label": peak_point["label"],
            "negativeRatio": peak_point["negativeRatio"],
            "riskCount": peak_point["riskCount"],
            "totalCount": peak_point["totalCount"],
        },
        "keywords": overall_terms,
        "points": points,
        "milestones": milestones[:3],
    }


def _build_analysis_diagnostics(result: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    platform = result.get("platform") or ""
    comment_count = int(result.get("commentCount", 0) or 0)
    coverage = result.get("coverageRate")
    degrade_reason = ((result.get("report") or {}).get("degrade_reason") or "").strip()

    if result.get("needsLogin"):
        diagnostics.append({
            "code": "login_required",
            "level": "warning",
            "title": "当前抓取受登录态影响",
            "impact": "评论样本可能明显偏少，情绪分布和聚类结果代表性会下降。",
            "action": result.get("loginHint") or ("请补充登录信息后重试分析。" if platform != "小红书" else "请先登录小红书后重试分析。"),
            "canContinue": True,
        })

    if result.get("playwrightMissing"):
        diagnostics.append({
            "code": "playwright_missing",
            "level": "warning",
            "title": "小红书签名服务不可用",
            "impact": "无法稳定翻页获取更多评论，常见表现是评论数为 0 或远低于公开评论数。",
            "action": "终端执行 playwright install chromium，完成后重启后端服务。",
            "canContinue": True,
        })

    if comment_count == 0:
        diagnostics.append({
            "code": "no_comments",
            "level": "danger",
            "title": "当前没有拿到可分析评论",
            "impact": "只能展示内容基础信息，舆情结论与风险判断都不可靠。",
            "action": "优先检查登录状态、平台限流、评论区是否关闭，确认后重试。",
            "canContinue": False,
        })
    elif coverage is not None and coverage < 25:
        diagnostics.append({
            "code": "low_coverage",
            "level": "warning",
            "title": "样本覆盖率偏低",
            "impact": f"当前样本仅覆盖约 {coverage}% 的公开评论，结果更适合快速参考，不适合直接做正式结论。",
            "action": "建议提高抓取页数，或补登录后重新分析。",
            "canContinue": True,
        })

    degrade_map = {
        "no_key": ("warning", "AI 报告已降级为模板", "无法生成 AI 深度总结与 Agent 推理结论。", "请配置可用的 LLM API Key 后重试。"),
        "insufficient_balance": ("warning", "AI 报告余额不足", "报告已退回模板模式，深度总结能力受限。", "请充值或更换可用的 API Key 后重试。"),
        "auth_failed": ("warning", "AI 报告鉴权失败", "报告已退回模板模式，AI 洞察未生成。", "请检查 API Key 是否正确、是否过期。"),
        "rate_limited": ("warning", "AI 报告触发限流", "本次未拿到完整 AI 总结。", "稍后重试，或切换更稳定的模型配置。"),
        "api_error": ("warning", "AI 报告调用失败", "本次未拿到完整 AI 总结。", "检查网络和模型服务状态后重试。"),
    }
    if degrade_reason and degrade_reason != "empty":
        level, title, impact, action = degrade_map.get(degrade_reason, degrade_map["api_error"])
        diagnostics.append({
            "code": "llm_degraded",
            "level": level,
            "title": title,
            "impact": impact,
            "action": action,
            "canContinue": True,
        })

    return diagnostics


def _build_confidence_meta(result: dict[str, Any]) -> dict[str, Any]:
    comment_count = int(result.get("commentCount", 0) or 0)
    coverage = result.get("coverageRate")
    diagnostics = result.get("diagnostics") or []
    cluster_count = len(result.get("clusters") or [])
    degrade_reason = ((result.get("report") or {}).get("degrade_reason") or "").strip()

    score = 95
    reasons: list[str] = []

    if comment_count == 0:
        score -= 60
        reasons.append("暂无可分析评论")
    elif comment_count < 5:
        score -= 35
        reasons.append("评论样本极少")
    elif comment_count < 20:
        score -= 20
        reasons.append("评论样本偏少")
    elif comment_count < 50:
        score -= 8
        reasons.append("样本规模一般")

    if coverage is not None:
        if coverage < 15:
            score -= 24
            reasons.append("样本覆盖率很低")
        elif coverage < 40:
            score -= 14
            reasons.append("样本覆盖率偏低")
        elif coverage < 70:
            score -= 6
            reasons.append("样本覆盖率中等")

    if result.get("needsLogin"):
        score -= 18
        reasons.append("登录缺失影响抓取完整性")
    if result.get("playwrightMissing"):
        score -= 10
        reasons.append("小红书签名服务不可用")
    if degrade_reason and degrade_reason != "empty":
        score -= 8
        reasons.append("AI 报告降级为模板")
    if cluster_count < 2 and comment_count >= 10:
        score -= 5
        reasons.append("观点聚类样本有限")
    if any(d.get("code") == "no_comments" for d in diagnostics):
        score = min(score, 28)

    score = max(20, min(98, score))
    if score >= 85:
        grade = "A"
        summary = "结果可信度高：样本相对充分，可直接用于判断当前舆情走向。"
    elif score >= 70:
        grade = "B"
        summary = "结果可信度较高：可用于分析，但建议结合原始评论做少量复核。"
    elif score >= 50:
        grade = "C"
        summary = "结果仅供参考：样本或链路存在限制，适合快速研判，不适合直接下结论。"
    else:
        grade = "D"
        summary = "结果可信度较低：建议先补齐登录或修复抓取问题，再重新分析。"

    return {
        "grade": grade,
        "score": score,
        "summary": summary,
        "reasons": reasons[:4],
    }


def _enrich_analysis_meta(result: dict[str, Any]) -> dict[str, Any]:
    result["publicCommentCount"] = _resolve_public_comment_count(result)
    result["coverageRate"] = _calc_coverage_rate(result)
    result["diagnostics"] = _build_analysis_diagnostics(result)
    result["confidence"] = _build_confidence_meta(result)
    return result


def _resolve_topic_public_comment_count(result: dict[str, Any]) -> int | None:
    total = 0
    known = False
    for item in result.get("videos") or []:
        value = item.get("publicCommentCount")
        if value in (None, ""):
            value = item.get("replyCountFromVideo", item.get("replyCountFromNote"))
        if value in (None, ""):
            continue
        try:
            total += int(value)
            known = True
        except (TypeError, ValueError):
            continue
    return total if known else None


def _calc_topic_coverage_rate(result: dict[str, Any]) -> float | None:
    public_count = result.get("publicCommentCount")
    total_comments = int(result.get("totalComments", 0) or 0)
    if public_count is None:
        return None
    try:
        public_count = int(public_count)
    except (TypeError, ValueError):
        return None
    if public_count <= 0:
        return None if total_comments == 0 else 100.0
    return round(min(100.0, total_comments * 100.0 / public_count), 1)


def _build_topic_diagnostics(result: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    items = result.get("videos") or []
    total_comments = int(result.get("totalComments", 0) or 0)
    success_items = [item for item in items if not item.get("error")]
    failed_items = [item for item in items if item.get("error")]
    coverage = result.get("coverageRate")
    platform = result.get("platform") or ("小红书" if result.get("type") == "xhs_topic" else "B站")

    if failed_items:
        diagnostics.append({
            "code": "partial_failed",
            "level": "warning",
            "title": "部分内容分析失败",
            "impact": f"当前仅成功分析 {len(success_items)}/{len(items)} 个{ '笔记' if platform == '小红书' else '视频' }，整体情绪与关键词可能偏向成功样本。",
            "action": "优先检查失败项的登录态、平台限流或链接可用性后重试。",
            "canContinue": True,
        })

    if any(item.get("needsLogin") for item in success_items):
        login_hint = next((item.get("loginHint") for item in success_items if item.get("loginHint")), "")
        diagnostics.append({
            "code": "login_required",
            "level": "warning",
            "title": "登录态会影响聚合样本完整性",
            "impact": f"{platform} 侧至少有一部分内容评论抓取受限，当前聚合结果可能低估负面或争议声量。",
            "action": login_hint or "补充登录后重新执行话题分析，可显著提升评论覆盖率。",
            "canContinue": True,
        })

    playwright_related = result.get("playwrightMissing") or any(item.get("playwrightMissing") for item in items) or any("playwright" in str(item.get("error", "")).lower() for item in failed_items)
    if platform == "小红书" and playwright_related:
        diagnostics.append({
            "code": "playwright_missing",
            "level": "warning",
            "title": "小红书签名依赖不可用",
            "impact": "无法稳定翻页获取更多评论，聚合样本可能明显偏少。",
            "action": "终端执行 playwright install chromium，完成后重启后端服务。",
            "canContinue": True,
        })

    if total_comments == 0:
        diagnostics.append({
            "code": "no_comments",
            "level": "danger",
            "title": "当前没有拿到可分析评论",
            "impact": "无法形成可靠的话题判断，当前结果只适合检查链路，不适合作结论。",
            "action": "优先补登录、排查限流或更换关键词后重新分析。",
            "canContinue": False,
        })
    elif coverage is not None and coverage < 25:
        diagnostics.append({
            "code": "low_coverage",
            "level": "warning",
            "title": "聚合样本覆盖率偏低",
            "impact": f"当前仅覆盖约 {coverage}% 的公开评论，更适合快速参考，不建议直接用于正式汇报。",
            "action": "建议补登录、提高抓取页数，或减少单次分析内容数量后重试。",
            "canContinue": True,
        })

    if result.get("llmSentimentEnhanced") is False and total_comments >= 30:
        diagnostics.append({
            "code": "llm_sentiment_off",
            "level": "warning",
            "title": "中性评论未做 LLM 二次增强",
            "impact": "情感分布完全依赖词典法，复杂语义与反讽评论可能被低估。",
            "action": "如需更细判断，可在设置中启用 LLM 情感增强。",
            "canContinue": True,
        })

    return diagnostics


def _build_topic_confidence_meta(result: dict[str, Any]) -> dict[str, Any]:
    total_comments = int(result.get("totalComments", 0) or 0)
    coverage = result.get("coverageRate")
    items = result.get("videos") or []
    success_count = sum(1 for item in items if not item.get("error"))
    failed_count = sum(1 for item in items if item.get("error"))
    score = 93
    reasons: list[str] = []

    if total_comments == 0:
        score -= 60
        reasons.append("暂无聚合评论样本")
    elif total_comments < 20:
        score -= 28
        reasons.append("聚合评论样本偏少")
    elif total_comments < 80:
        score -= 12
        reasons.append("样本规模一般")

    if coverage is not None:
        if coverage < 15:
            score -= 22
            reasons.append("公开评论覆盖率很低")
        elif coverage < 40:
            score -= 12
            reasons.append("公开评论覆盖率偏低")
        elif coverage < 70:
            score -= 6
            reasons.append("覆盖率中等")

    if failed_count:
        score -= min(20, failed_count * 6)
        reasons.append(f"存在 {failed_count} 个内容分析失败")
    if success_count and success_count < max(2, len(items)):
        reasons.append(f"成功分析 {success_count}/{len(items)} 个内容")
    if any(item.get("needsLogin") for item in items):
        score -= 12
        reasons.append("登录缺失影响部分样本完整性")
    if result.get("playwrightMissing") or any(item.get("playwrightMissing") for item in items) or any("playwright" in str(item.get("error", "")).lower() for item in items):
        score -= 8
        reasons.append("小红书签名依赖未就绪")
    if len(result.get("clusters") or []) < 2 and total_comments >= 15:
        score -= 5
        reasons.append("主题聚类信号有限")

    score = max(20, min(98, score))
    if score >= 85:
        grade = "A"
        summary = "聚合结果可信度高：样本较充分，可直接用于判断话题整体舆情。"
    elif score >= 70:
        grade = "B"
        summary = "聚合结果可信度较高：可用于分析，但建议抽查失败项或少量原始评论。"
    elif score >= 50:
        grade = "C"
        summary = "聚合结果仅供参考：样本或链路存在限制，更适合快速研判。"
    else:
        grade = "D"
        summary = "聚合结果可信度较低：建议先修复抓取链路或补齐登录后再分析。"

    return {
        "grade": grade,
        "score": score,
        "summary": summary,
        "reasons": reasons[:4],
    }


def _enrich_topic_meta(result: dict[str, Any]) -> dict[str, Any]:
    items = result.get("videos") or []
    result["successCount"] = sum(1 for item in items if not item.get("error"))
    result["failedCount"] = sum(1 for item in items if item.get("error"))
    result["publicCommentCount"] = _resolve_topic_public_comment_count(result)
    result["coverageRate"] = _calc_topic_coverage_rate(result)
    result["diagnostics"] = _build_topic_diagnostics(result)
    result["confidence"] = _build_topic_confidence_meta(result)
    return result


def _build_compare_diagnostics(result: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    bili = result.get("bilibili")
    xhs = result.get("xiaohongshu")

    if not (bili and xhs):
        missing = []
        if not bili:
            missing.append("B站")
        if not xhs:
            missing.append("小红书")
        diagnostics.append({
            "code": "platform_missing",
            "level": "danger",
            "title": "跨平台对比不完整",
            "impact": f"当前缺少 {'、'.join(missing)} 侧结果，只能参考单平台表现，无法可靠判断平台差异。",
            "action": "优先修复失败平台的登录、Cookie 或依赖问题后重新对比。",
            "canContinue": False,
        })

    for key, label, data in (("bilibili", "B站", bili), ("xiaohongshu", "小红书", xhs)):
        if not data:
            continue
        conf = data.get("confidence") or {}
        if conf.get("grade") in ("C", "D"):
            diagnostics.append({
                "code": f"{key}_low_confidence",
                "level": "warning",
                "title": f"{label}侧样本可信度偏低",
                "impact": f"{label} 当前可信度为 {conf.get('grade')}（{conf.get('score')} 分），对比结论容易被样本缺口放大。",
                "action": (data.get("diagnostics") or [{}])[0].get("action") or f"先提升 {label} 侧评论覆盖率后再进行横向比较。",
                "canContinue": True,
            })
    return diagnostics


def _build_compare_confidence_meta(result: dict[str, Any]) -> dict[str, Any]:
    bili = result.get("bilibili")
    xhs = result.get("xiaohongshu")
    scores = [item.get("confidence", {}).get("score") for item in (bili, xhs) if item and item.get("confidence")]
    score = round(sum(scores) / len(scores)) if scores else 35
    reasons: list[str] = []
    if bili and bili.get("confidence"):
        reasons.append(f"B站可信度 {bili['confidence'].get('grade')} / {bili['confidence'].get('score')} 分")
    if xhs and xhs.get("confidence"):
        reasons.append(f"小红书可信度 {xhs['confidence'].get('grade')} / {xhs['confidence'].get('score')} 分")
    if not (bili and xhs):
        score -= 18
        reasons.append("缺少一侧平台结果，横向对比不完整")

    score = max(20, min(98, score))
    if score >= 85 and bili and xhs:
        grade = "A"
        summary = "跨平台对比可信度高：双平台样本都较完整，可以直接比较差异。"
    elif score >= 70 and bili and xhs:
        grade = "B"
        summary = "跨平台对比可信度较高：可用于分析差异，但建议抽查关键评论。"
    elif score >= 50:
        grade = "C"
        summary = "跨平台对比仅供参考：至少一侧样本存在限制，差异结论需谨慎。"
    else:
        grade = "D"
        summary = "跨平台对比可信度较低：建议先修复失败平台或提升样本后再对比。"

    return {
        "grade": grade,
        "score": score,
        "summary": summary,
        "reasons": reasons[:4],
    }


def _enrich_compare_meta(result: dict[str, Any]) -> dict[str, Any]:
    result["diagnostics"] = _build_compare_diagnostics(result)
    result["confidence"] = _build_compare_confidence_meta(result)
    return result


def analyze_url(raw_url: str, pages: int = 5) -> dict[str, Any]:
    logger.info(f"开始分析：url={raw_url} pages={pages}")
    final_url, bvid = resolve_bvid(raw_url)
    video = fetch_video_info(bvid)
    replies_raw = fetch_replies(int(video["aid"]), pages=pages)
    replies, dedupe_stats = dedupe_comments(replies_raw)
    logger.info(f"分析评论：原始 {len(replies_raw)} → 清洗 {len(replies)}（{dedupe_stats}）")

    for reply in replies:
        reply["sentiment"] = score_text(reply["text"])["label"]

    # LLM 增强情感分析：对词典法判为"中性"的评论做二次分类
    # 复用现有 LLM 通道，零新增依赖；无 key 或失败时自动跳过，保持词典法结果
    llm_sentiment_stats = {"total_neutral": 0, "enhanced": 0, "unchanged": 0}
    if _LLM_SENTIMENT_OK and enhance_neutral_comments is not None:
        try:
            llm_sentiment_stats = enhance_neutral_comments(replies)
            if llm_sentiment_stats["enhanced"] > 0:
                logger.info(
                    f"LLM 情感增强：{llm_sentiment_stats['total_neutral']} 条中性评论 → "
                    f"{llm_sentiment_stats['enhanced']} 条重新分类"
                )
        except Exception as exc:
            logger.warning(f"LLM 情感增强失败，保持词典法结果：{exc}")

    dist_counter = Counter(reply["sentiment"] for reply in replies)
    sentiments = {key: dist_counter.get(key, 0) for key in ["pos", "neu", "neg", "con", "risk"]}
    total = max(1, sum(sentiments.values()))
    sentiment_percent = {key: round(value * 100 / total, 1) for key, value in sentiments.items()}
    risk, reason = risk_level(sentiments, len(replies))
    keywords = extract_keywords(replies)
    keywords_weighted = extract_keywords_weighted(replies)
    clusters = build_clusters(replies)
    negative_timeline = _build_negative_timeline(replies)
    hot_comments = sorted(replies, key=lambda x: x.get("likes", 0), reverse=True)[:30]

    stat = video.get("stat") or {}
    owner = video.get("owner") or {}
    public_reply_count = int(stat.get("reply", 0) or 0)
    needs_login = public_reply_count >= 20 and len(replies) <= 5 and "SESSDATA" not in load_user_cookies()
    result = {
        "sourceUrl": raw_url,
        "finalUrl": final_url,
        "bvid": bvid,
        "title": video.get("title"),
        "author": owner.get("name"),
        "authorMid": owner.get("mid"),
        "platform": "B站",
        "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(video.get("pubdate", 0))),
        "desc": video.get("desc"),
        "pic": video.get("pic"),
        "views": stat.get("view", 0),
        "likes": stat.get("like", 0),
        "coins": stat.get("coin", 0),
        "favorites": stat.get("favorite", 0),
        "shares": stat.get("share", 0),
        "danmaku": stat.get("danmaku", 0),
        "replyCountFromVideo": public_reply_count,
        "commentCount": len(replies),
        "rawCommentCount": len(replies_raw),
        "dedupeStats": dedupe_stats,
        "llmSentimentEnhanced": _LLM_SENTIMENT_OK,
        "llmSentimentStats": llm_sentiment_stats,
        "needsLogin": needs_login,
        "loginHint": (
            "B站对未登录请求做了限流，只返回 3 条精选评论。"
            "请在项目目录下创建 cookies.txt 并写入浏览器中登录后的 SESSDATA=xxx，"
            "或设置同名环境变量后重启后端，即可抓取全部公开评论。"
        ) if needs_login else "",
        "risk": risk,
        "riskReason": reason,
        "sentiments": sentiment_percent,
        "sentimentCounts": sentiments,
        "keywords": keywords,
        "keywordsWeighted": keywords_weighted,
        "clusters": clusters,
        "negativeTimeline": negative_timeline,
        "comments": hot_comments,
        "report": make_report(video, replies, sentiments, keywords, clusters),
        "fetchedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return _enrich_analysis_meta(result)


def analyze_xhs_url(raw_url: str, pages: int = 5) -> dict[str, Any]:
    """分析小红书笔记评论。"""
    logger.info(f"开始小红书分析：url={raw_url} pages={pages}")
    try:
        final_url, note_id, xsec_token = xhs_client.resolve_note_id(raw_url)
        logger.info(f"链接解析成功：note_id={note_id} xsec_token={'有' if xsec_token else '无'}")
    except Exception as exc:
        logger.error(f"链接解析失败：{exc}")
        raise RuntimeError(f"链接解析失败：{exc}") from exc
    
    try:
        note_info = xhs_client.fetch_note_info(note_id, xsec_token)
        logger.info(f"笔记详情获取成功：title={note_info.get('title', '')[:30]} author={note_info.get('user', {}).get('nickname', '')}")
    except Exception as exc:
        logger.error(f"笔记详情获取失败：{exc}")
        raise RuntimeError(f"获取笔记详情失败：{exc}") from exc
    
    # 优先使用笔记返回的 xsec_token
    token = xsec_token or note_info.get("xsecToken", "")
    
    try:
        comments_raw = xhs_client.fetch_comments(note_id, token, max_pages=pages, note_info=note_info)
        logger.info(f"评论获取完成：共 {len(comments_raw)} 条")
    except Exception as exc:
        logger.error(f"评论获取失败：{exc}")
        raise RuntimeError(f"获取评论失败：{exc}") from exc
    
    # 复用现有分析管线
    for c in comments_raw:
        c["sentiment"] = score_text(c["text"])["label"]
    
    dist_counter = Counter(c["sentiment"] for c in comments_raw)
    sentiments = {key: dist_counter.get(key, 0) for key in ["pos", "neu", "neg", "con", "risk"]}
    total = max(1, sum(sentiments.values()))
    sentiment_percent = {key: round(value * 100 / total, 1) for key, value in sentiments.items()}
    risk, reason = risk_level(sentiments, len(comments_raw))
    keywords = extract_keywords(comments_raw)
    keywords_weighted = extract_keywords_weighted(comments_raw)
    clusters = build_clusters(comments_raw)
    negative_timeline = _build_negative_timeline(comments_raw)
    hot_comments = sorted(comments_raw, key=lambda x: x.get("likes", 0), reverse=True)[:30]
    
    logger.info(f"分析完成：sentiments={sentiments} risk={risk} keywords={len(keywords)} clusters={len(clusters)}")
    
    user = note_info.get("user", {})
    interact = note_info.get("interactInfo", {})
    
    # 构建用于报告的类 video 结构
    note_for_report = {
        "title": note_info.get("title", ""),
        "desc": note_info.get("desc", ""),
        "author": user.get("nickname", ""),
    }
    
    reply_count_from_note = int(interact.get("commentCount", 0) or 0)
    # 仅在以下情况提示"需要登录"：
    # 1. 完全没有获取到评论（0 条）→ 肯定是登录/限流问题
    # 2. 获取到少量评论（≤5 条）且笔记实际评论数远大于此（>15 条）→ 可能被限流
    # 如果笔记本身就只有几条评论，不应该提示"抓取不全"
    needs_login = len(comments_raw) == 0 or (
        len(comments_raw) <= 5 and reply_count_from_note > 15
    )
    xhs_cookies = xhs_client.load_xhs_cookies()
    # 检测 Playwright 是否可用，用于给出精确的诊断提示
    playwright_available = False
    try:
        from analysis.xhs_login import _sign
        playwright_available = True
    except Exception:
        pass

    login_hint_parts = []
    if needs_login:
        if not xhs_cookies.get("a1"):
            login_hint_parts.append("Cookie 未配置（缺少 a1/web_session）：点击右上角「登录 小红书」扫码配置。")
        elif not playwright_available:
            login_hint_parts.append("Playwright 签名服务不可用：终端执行 playwright install chromium 并重启服务器。")
        else:
            login_hint_parts.append("Cookie 可能已过期：请重新登录小红书。")
    login_hint = "".join(login_hint_parts)

    result = {
        "sourceUrl": raw_url,
        "finalUrl": final_url,
        "noteId": note_id,
        "title": note_info.get("title", ""),
        "author": user.get("nickname", ""),
        "authorId": user.get("userId", ""),
        "platform": "小红书",
        "time": note_info.get("time", 0),  # Unix 时间戳
        "desc": note_info.get("desc", ""),
        "type": note_info.get("type", ""),
        "ipLocation": note_info.get("ipLocation", ""),
        "pic": note_info.get("imageList", [{}])[0].get("url", "") if note_info.get("imageList") else "",
        "likes": interact.get("likes", "0"),
        "collected": interact.get("collectedCount", "0"),
        "commentCount": len(comments_raw),
        "replyCountFromNote": reply_count_from_note,
        "needsLogin": needs_login,
        "playwrightMissing": not playwright_available,
        "loginHint": login_hint,
        "risk": risk,
        "riskReason": reason,
        "sentiments": sentiment_percent,
        "sentimentCounts": sentiments,
        "keywords": keywords,
        "keywordsWeighted": keywords_weighted,
        "clusters": clusters,
        "negativeTimeline": negative_timeline,
        "comments": hot_comments,
        "report": make_report(note_for_report, comments_raw, sentiments, keywords, clusters),
        "fetchedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return _enrich_analysis_meta(result)


def _calc_history_baseline(history: list[dict]) -> dict[str, float] | None:
    """从历史记录中计算情绪分布均值基线。"""
    if not history:
        return None
    sums = {"pos": 0.0, "neu": 0.0, "neg": 0.0, "con": 0.0, "risk": 0.0}
    count = 0
    for entry in history:
        result = entry.get("result")
        if not result:
            continue
        sents = result.get("sentiments", {})
        if isinstance(sents, dict):
            for k in sums:
                sums[k] += float(sents.get(k, 0))
            count += 1
    if count == 0:
        return None
    return {k: round(v / count, 1) for k, v in sums.items()}


def result_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": result.get("title"),
        "bvid": result.get("bvid"),
        "author": result.get("author"),
        "pic": result.get("pic"),
        "risk": result.get("risk"),
        "riskReason": result.get("riskReason"),
        "commentCount": result.get("commentCount"),
        "replyCountFromVideo": result.get("replyCountFromVideo"),
        "replyCountFromNote": result.get("replyCountFromNote"),
        "publicCommentCount": result.get("publicCommentCount"),
        "coverageRate": result.get("coverageRate"),
        "confidence": result.get("confidence"),
        "diagnostics": result.get("diagnostics"),
        "playwrightMissing": result.get("playwrightMissing", False),
        "needsLogin": result.get("needsLogin", False),
        "loginHint": result.get("loginHint", ""),
        "sentiments": result.get("sentiments"),
        "sentimentCounts": result.get("sentimentCounts"),
        "keywords": result.get("keywords"),
        "fetchedAt": result.get("fetchedAt"),
        "finalUrl": result.get("finalUrl"),
    }


def find_monitor(data: dict[str, Any], monitor_id: str) -> dict[str, Any] | None:
    for monitor in data.get("monitors", []):
        if monitor.get("id") == monitor_id:
            return monitor
    return None


def run_monitor_once(monitor_id: str, manual: bool = False) -> dict[str, Any]:
    with DATA_LOCK:
        data = load_db()
        monitor = find_monitor(data, monitor_id)
        if not monitor:
            raise ValueError("监测任务不存在。")
        if monitor.get("status") == "running":
            logger.info(f"任务 {monitor_id} 仍在执行中，跳过此次请求。")
            return {"status": "running", "message": "该任务正在检测中，请稍后。"}
        monitor["status"] = "running"
        monitor["lastError"] = ""
        monitor["updatedAt"] = fmt_ts()
        save_db(data)

    logger.info(
        f"运行监测任务 id={monitor_id} url={monitor.get('url')} "
        f"manual={manual} pages={monitor.get('pages')}"
    )
    started = now_ts()
    try:
        result = analyze_url(monitor["url"], int(monitor.get("pages", 5)))
        summary = result_summary(result)
        entry = {
            "id": uuid4().hex,
            "type": "manual" if manual else "auto",
            "ok": True,
            "startedAt": fmt_ts(started),
            "finishedAt": fmt_ts(),
            "result": result,
            "summary": summary,
        }
        with DATA_LOCK:
            data = load_db()
            monitor = find_monitor(data, monitor_id)
            if monitor:
                monitor["title"] = result.get("title") or monitor.get("title") or "未命名视频"
                monitor["bvid"] = result.get("bvid")
                monitor["author"] = result.get("author")
                monitor["pic"] = result.get("pic")
                monitor["lastRun"] = fmt_ts()
                monitor["lastRunTs"] = now_ts()
                monitor["nextRunTs"] = now_ts() + interval_seconds(monitor.get("intervalValue", 1), monitor.get("intervalUnit", "小时"))
                monitor["nextRun"] = fmt_ts(monitor["nextRunTs"])
                monitor["status"] = "ok"
                monitor["lastError"] = ""
                monitor["lastResult"] = summary
                history = monitor.setdefault("history", [])
                history.insert(0, entry)
                monitor["history"] = history[:30]
                monitor["updatedAt"] = fmt_ts()
                save_db(data)
        logger.info(
            f"任务完成 id={monitor_id} 评论={summary.get('commentCount')} "
            f"风险={summary.get('risk')}"
        )
        # 高风险时触发 Webhook 告警（异步、不阻塞主流程，失败也不影响任务结果）
        try:
            from analysis.alert import send_alert as _send_alert
            risk_val = summary.get("risk") or "unknown"
            _send_alert(
                monitor_id=monitor_id,
                risk=risk_val,
                title=summary.get("title") or monitor.get("title") or "未命名视频",
                text=summary.get("riskReason") or "",
                url=monitor.get("url", ""),
                sentiments=summary.get("sentiments"),
                keywords=summary.get("keywords", [])[:10],
                top_neg_comments=[c.get("text", "") for c in (result.get("comments") or []) if c.get("sentiment") in ("neg", "risk")][:5],
                history_baseline=_calc_history_baseline(monitor.get("history", [])),
            )
        except Exception as alert_exc:
            logger.debug(f"告警发送异常（忽略）：{alert_exc}")
        return {"status": "ok", "result": summary}
    except Exception as exc:
        logger.exception(f"任务失败 id={monitor_id}：{exc}")
        with DATA_LOCK:
            data = load_db()
            monitor = find_monitor(data, monitor_id)
            if monitor:
                monitor["lastRun"] = fmt_ts()
                monitor["lastRunTs"] = now_ts()
                monitor["nextRunTs"] = now_ts() + interval_seconds(monitor.get("intervalValue", 1), monitor.get("intervalUnit", "小时"))
                monitor["nextRun"] = fmt_ts(monitor["nextRunTs"])
                monitor["status"] = "error"
                monitor["lastError"] = str(exc)
                history = monitor.setdefault("history", [])
                history.insert(0, {
                    "id": uuid4().hex,
                    "type": "manual" if manual else "auto",
                    "ok": False,
                    "startedAt": fmt_ts(started),
                    "finishedAt": fmt_ts(),
                    "error": str(exc),
                })
                monitor["history"] = history[:30]
                monitor["updatedAt"] = fmt_ts()
                save_db(data)
        raise


def save_user_cookies(cookies: dict[str, str]) -> None:
    """将登录得到的 Cookie 持久化到 cookies.txt，下次启动可自动加载。"""
    try:
        lines = [f"{k}={v}" for k, v in cookies.items() if v]
        COOKIE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(f"已写入 cookies.txt（{len(lines)} 项）")
    except Exception as exc:
        logger.warning(f"写入 cookies.txt 失败：{exc}")


def login_qrcode_generate() -> dict[str, Any]:
    """申请 B 站扫码登录二维码，返回 url 和 qrcode_key。"""
    bootstrap_session()
    data = http_get_json("https://passport.bilibili.com/x/passport-login/web/qrcode/generate")
    if data.get("code") != 0:
        raise RuntimeError(f"申请二维码失败：{data.get('message') or data}")
    d = data.get("data") or {}
    return {"url": d.get("url"), "qrcodeKey": d.get("qrcode_key")}


def login_qrcode_poll(qrcode_key: str) -> dict[str, Any]:
    """轮询扫码结果。code: 0=成功 86101=未扫码 86090=已扫未确认 86038=已过期。"""
    if not qrcode_key:
        raise ValueError("缺少 qrcodeKey。")
    bootstrap_session()
    data = http_get_json(
        "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
        {"qrcode_key": qrcode_key},
    )
    d = data.get("data") or {}
    status_code = int(d.get("code", -1))
    result: dict[str, Any] = {
        "code": status_code,
        "message": d.get("message") or "",
        "url": d.get("url") or "",
    }
    if status_code == 0:
        # 登录成功，CookieJar 中已自动保存 SESSDATA 等
        cookies = {c.name: c.value for c in COOKIE_JAR if "bilibili" in (c.domain or "")}
        keep = {k: cookies[k] for k in ("SESSDATA", "bili_jct", "DedeUserID", "DedeUserID__ckMd5", "buvid3", "sid") if k in cookies}
        save_user_cookies(keep)
        result["cookies"] = {k: f"...{v[-6:]}" for k, v in keep.items() if v}
        logger.info(f"扫码登录成功，已保存 Cookie：{list(keep.keys())}")
    return result


def scheduler_loop() -> None:
    logger.info("调度线程启动，每 30 秒巡检一次。")
    from concurrent.futures import ThreadPoolExecutor
    # 并发上限：B站对高并发会风控（412），2-3 个并发既能避免慢任务阻塞其他任务，
    # 又不易触发限流。run_monitor_once 内部用 DATA_LOCK 保证 load→改→save 原子性，
    # 同一任务不会被重复执行（开头会检查 status==running 并抢占标记）。
    max_workers = 3
    while True:
        try:
            due_ids: list[str] = []
            current = now_ts()
            data = load_db()
            for monitor in data.get("monitors", []):
                if not monitor.get("enabled", True):
                    continue
                if monitor.get("status") == "running":
                    continue
                if int(monitor.get("nextRunTs") or 0) <= current:
                    due_ids.append(monitor["id"])
            if due_ids:
                logger.info(f"调度器：本轮触发 {len(due_ids)} 个任务 -> {due_ids}")
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="monitor") as ex:
                    futures = {ex.submit(run_monitor_once, mid, False): mid for mid in due_ids}
                    for fut, mid in futures.items():
                        try:
                            fut.result()
                        except Exception as exc:
                            logger.warning(f"自动检测失败：{mid} {exc}")
        except Exception as exc:
            logger.exception(f"调度器异常：{exc}")
        time.sleep(30)


VUE_DIST = ROOT / "frontend" / "dist"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # 优先从 Vue 构建产物目录 serve 静态文件，fallback 到项目根目录
        serve_dir = str(VUE_DIST) if VUE_DIST.is_dir() else str(ROOT)
        super().__init__(*args, directory=serve_dir, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.debug("HTTP %s - %s", self.address_string(), format % args)

    def _client_is_local(self) -> bool:
        """判断请求是否来自本机回环地址。"""
        try:
            return self.client_address[0] in ("127.0.0.1", "::1", "localhost")
        except Exception:
            return False

    def _check_write_auth(self) -> bool:
        """写接口鉴权。
        - 本机（回环地址）直接放行，本地单用户使用无感；
        - 非本机需携带 Authorization: Bearer <token>，token 与环境变量 AUTH_TOKEN 匹配；
        - 未设置 AUTH_TOKEN 时，非本机写请求一律拒绝（默认只读局域网访问）。
        这样既不破坏本地体验，又避免任意局域网用户删除/修改监测任务或触发登录。
        """
        if self._client_is_local():
            return True
        import os
        expected = os.environ.get("AUTH_TOKEN", "").strip()
        if not expected:
            return False
        auth = self.headers.get("Authorization", "") or ""
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        return bool(token) and token == expected

    def json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def binary_response(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw or "{}")

    def do_OPTIONS(self) -> None:
        self.json_response(200, {"ok": True})

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/"):
            logger.info(f"GET {self.path}")

        if parsed.path == "/api/image":
            query = urllib.parse.parse_qs(parsed.query)
            image_url = (query.get("url") or [""])[0].strip()
            try:
                body, content_type = http_get_binary(image_url)
                self.binary_response(200, body, content_type)
            except Exception as exc:
                logger.warning(f"图片代理失败：{image_url} {exc}")
                self.json_response(400, {"ok": False, "error": str(exc)})
            return

        # /api/auth/token — 返回 AUTH_TOKEN 给前端（用于远程部署时 POST 鉴权）
        # 仅在 AUTH_TOKEN 已设置时返回，否则返回空，前端据此决定是否携带 Authorization 头
        if parsed.path == "/api/auth/token":
            token = os.environ.get("AUTH_TOKEN", "").strip()
            self.json_response(200, {"ok": True, "token": token})
            return

        if parsed.path == "/api/analyze":
            query = urllib.parse.parse_qs(parsed.query)
            raw_url = (query.get("url") or [""])[0]
            pages = int((query.get("pages") or ["5"])[0])
            try:
                data = analyze_url(raw_url, pages)
                self.json_response(200, {"ok": True, "data": data})
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                self.json_response(502, {"ok": False, "error": f"网络或平台接口访问失败：{exc}"})
            except Exception as exc:
                self.json_response(400, {"ok": False, "error": str(exc)})
            return

        if parsed.path == "/api/monitors":
            data = load_db()
            self.json_response(200, {"ok": True, "monitors": [public_monitor(m) for m in data.get("monitors", [])]})
            return

        if parsed.path == "/api/login/status":
            cookies = load_user_cookies()
            logged_in = bool(cookies.get("SESSDATA"))
            self.json_response(200, {
                "ok": True,
                "loggedIn": logged_in,
                "uid": cookies.get("DedeUserID", ""),
                "hint": "" if logged_in else "尚未登录，未登录时 B站只会下发 3 条精选评论。点击右上角“登录 B站”按钮扫码登录。",
            })
            return

        if parsed.path == "/api/config/llm":
            # 读取当前配置（不返回 key 明文，只返回是否已配置 + 前4位掩码）
            env_map = _read_env_file()
            api_key = env_map.get("LLM_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
            key_masked = ""
            if api_key:
                key_masked = api_key[:4] + "***" + (api_key[-4:] if len(api_key) > 8 else "")
            self.json_response(200, {
                "ok": True,
                "available": bool(_llm_available()),
                "apiKey": key_masked,
                "apiKeySet": bool(api_key),
                "baseUrl": env_map.get("LLM_BASE_URL") or os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1"),
                "model": env_map.get("LLM_MODEL") or os.environ.get("LLM_MODEL", "deepseek-chat"),
                "timeout": int(env_map.get("LLM_TIMEOUT") or os.environ.get("LLM_TIMEOUT", "30")),
                "presets": LLM_PRESETS,
            })
            return

        if parsed.path == "/api/config/alert":
            # 读取当前告警配置
            env_map = _read_env_file()
            webhook_url = env_map.get("ALERT_WEBHOOK_URL", "") or os.environ.get("ALERT_WEBHOOK_URL", "")
            min_risk = env_map.get("ALERT_MIN_RISK", "") or os.environ.get("ALERT_MIN_RISK", "high")
            cooldown = env_map.get("ALERT_COOLDOWN_SEC", "") or os.environ.get("ALERT_COOLDOWN_SEC", "3600")
            # 识别平台
            platform = "none"
            if webhook_url:
                try:
                    from analysis.alert import _detect_platform
                    platform = _detect_platform(webhook_url)
                except Exception:
                    platform = "generic"
            self.json_response(200, {
                "ok": True,
                "configured": bool(webhook_url),
                "webhookUrl": webhook_url,
                "minRisk": min_risk,
                "cooldown": int(cooldown) if str(cooldown).isdigit() else 3600,
                "platform": platform,
            })
            return

        if parsed.path == "/api/monitor/history":
            query = urllib.parse.parse_qs(parsed.query)
            monitor_id = (query.get("id") or [""])[0]
            data = load_db()
            monitor = find_monitor(data, monitor_id)
            if not monitor:
                self.json_response(404, {"ok": False, "error": "监测任务不存在。"})
                return
            self.json_response(200, {"ok": True, "monitor": public_monitor(monitor), "history": monitor.get("history", [])})
            return

        if parsed.path == "/api/topic/search":
            query = urllib.parse.parse_qs(parsed.query)
            keyword = (query.get("keyword") or [""])[0].strip()
            page = int((query.get("page") or ["1"])[0])
            page_size = int((query.get("pageSize") or ["20"])[0])
            order = (query.get("order") or ["totalrank"])[0]
            if not keyword:
                self.json_response(400, {"ok": False, "error": "请输入搜索关键词。"})
                return
            try:
                result = search_bilibili_videos(keyword, page=page, page_size=page_size, order=order)
                self.json_response(200, {"ok": True, "data": result})
            except Exception as exc:
                self.json_response(502, {"ok": False, "error": f"搜索失败：{exc}"})
            return

        if parsed.path == "/api/topic/analyze":
            query = urllib.parse.parse_qs(parsed.query)
            keyword = (query.get("keyword") or [""])[0].strip()
            top_n = int((query.get("topN") or ["5"])[0])
            pages = int((query.get("pages") or ["3"])[0])
            if not keyword:
                self.json_response(400, {"ok": False, "error": "请输入话题关键词。"})
                return
            try:
                result = analyze_topic(keyword, top_n=min(max(1, top_n), 10), pages_per_video=min(max(1, pages), 10))
                self.json_response(200, {"ok": True, "data": result})
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                self.json_response(502, {"ok": False, "error": f"网络或平台接口访问失败：{exc}"})
            except Exception as exc:
                self.json_response(400, {"ok": False, "error": str(exc)})
            return

        if parsed.path == "/api/topic/compare":
            query = urllib.parse.parse_qs(parsed.query)
            keyword = (query.get("keyword") or [""])[0].strip()
            top_n = int((query.get("topN") or ["5"])[0])
            pages = int((query.get("pages") or ["3"])[0])
            if not keyword:
                self.json_response(400, {"ok": False, "error": "请输入话题关键词。"})
                return
            try:
                result = analyze_topic_compare(keyword, top_n=min(max(1, top_n), 10), pages=min(max(1, pages), 10))
                self.json_response(200, {"ok": True, "data": result})
            except RuntimeError as exc:
                self.json_response(502, {"ok": False, "error": str(exc)})
            except Exception as exc:
                self.json_response(400, {"ok": False, "error": str(exc)})
            return

        # ---- 小红书 API ----

        if parsed.path == "/api/xhs/analyze":
            query = urllib.parse.parse_qs(parsed.query)
            url = (query.get("url") or [""])[0].strip()
            pages = int((query.get("pages") or ["5"])[0])
            if not url:
                self.json_response(400, {"ok": False, "error": "请输入小红书笔记链接。"})
                return
            try:
                result = analyze_xhs_url(url, pages=min(max(1, pages), 20))
                self.json_response(200, {"ok": True, "data": result})
            except RuntimeError as exc:
                self.json_response(502, {"ok": False, "error": str(exc)})
            except Exception as exc:
                logger.exception("小红书分析异常")
                self.json_response(500, {"ok": False, "error": f"分析失败：{exc}"})
            return

        # 小红书 Cookie 状态
        if parsed.path == "/api/xhs/login/status":
            cookies = xhs_client.load_xhs_cookies()
            configured = bool(cookies.get("a1"))
            # 额外检测 Playwright 是否可用
            playwright_ok = False
            playwright_missing = False
            try:
                import playwright  # noqa: F401
                # 检查可执行文件是否存在
                import subprocess
                result_check = subprocess.run(
                    ["python", "-c", "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); p.stop()"],
                    capture_output=True, timeout=5
                )
                playwright_ok = result_check.returncode == 0
                playwright_missing = not playwright_ok and ("Executable doesn't exist" in result_check.stderr.decode("utf-8", "replace") or "playwright install" in result_check.stderr.decode("utf-8", "replace"))
            except Exception:
                playwright_missing = True
            self.json_response(200, {
                "ok": True,
                "data": {
                    "configured": configured,
                    "playwrightOk": playwright_ok,
                    "playwrightMissing": playwright_missing,
                    "cookies": {k: v for k, v in cookies.items()} if configured else {},
                },
            })
            return

        if parsed.path == "/api/xhs/search":
            query = urllib.parse.parse_qs(parsed.query)
            keyword = (query.get("keyword") or [""])[0].strip()
            page = int((query.get("page") or ["1"])[0])
            page_size = int((query.get("pageSize") or ["20"])[0])
            if not keyword:
                self.json_response(400, {"ok": False, "error": "请输入搜索关键词。"})
                return
            try:
                result = xhs_client.search_notes(keyword, page=page, page_size=page_size)
                self.json_response(200, {"ok": True, "data": result})
            except Exception as exc:
                self.json_response(502, {"ok": False, "error": f"搜索失败：{exc}"})
            return

        if parsed.path == "/api/xhs/topic/analyze":
            query = urllib.parse.parse_qs(parsed.query)
            keyword = (query.get("keyword") or [""])[0].strip()
            top_n = int((query.get("topN") or ["5"])[0])
            pages = int((query.get("pages") or ["3"])[0])
            if not keyword:
                self.json_response(400, {"ok": False, "error": "请输入话题关键词。"})
                return
            try:
                result = analyze_xhs_topic(keyword, top_n=min(max(1, top_n), 10), pages_per_note=min(max(1, pages), 10))
                self.json_response(200, {"ok": True, "data": result})
            except Exception as exc:
                self.json_response(502, {"ok": False, "error": str(exc)})
            return

        # ---- 阶段三：策略生成 Agent / 趋势分析 API ----

        if parsed.path == "/api/agent/trace":
            query = urllib.parse.parse_qs(parsed.query)
            monitor_id = (query.get("monitor_id") or [""])[0].strip()
            if not monitor_id:
                self.json_response(400, {"ok": False, "error": "缺少 monitor_id 参数。"})
                return
            try:
                data = load_db()
                monitor = find_monitor(data, monitor_id)
                if not monitor:
                    self.json_response(404, {"ok": False, "error": "监测任务不存在。"})
                    return
                history = monitor.get("history", [])
                # 取最近一次成功分析的推理轨迹
                trace = []
                for entry in history[:5]:
                    if not entry.get("ok"):
                        continue
                    result = entry.get("result", {})
                    trace.append({
                        "fetchedAt": entry.get("finishedAt", ""),
                        "risk": result.get("risk", "unknown"),
                        "riskReason": result.get("riskReason", ""),
                        "sentiments": result.get("sentiments", {}),
                        "keywords": result.get("keywords", [])[:10],
                        "commentCount": result.get("commentCount", 0),
                        "title": result.get("title", ""),
                    })
                self.json_response(200, {"ok": True, "monitorId": monitor_id, "trace": trace})
            except Exception as exc:
                self.json_response(500, {"ok": False, "error": f"获取推理轨迹失败：{exc}"})
            return

        if parsed.path == "/api/trend/up":
            query = urllib.parse.parse_qs(parsed.query)
            author = (query.get("author") or [""])[0].strip()
            limit = int((query.get("limit") or ["5"])[0])
            if not author:
                self.json_response(400, {"ok": False, "error": "缺少 author 参数。"})
                return
            try:
                results = _get_up_trend(author, limit=min(max(1, limit), 20))
                self.json_response(200, {"ok": True, "author": author, "items": results})
            except Exception as exc:
                self.json_response(500, {"ok": False, "error": f"获取 UP 主趋势失败：{exc}"})
            return

        if parsed.path == "/api/trend/topic":
            query = urllib.parse.parse_qs(parsed.query)
            keyword = (query.get("keyword") or [""])[0].strip()
            limit = int((query.get("limit") or ["5"])[0])
            if not keyword:
                self.json_response(400, {"ok": False, "error": "缺少 keyword 参数。"})
                return
            try:
                results = _get_topic_trend(keyword, limit=min(max(1, limit), 20))
                self.json_response(200, {"ok": True, "keyword": keyword, "items": results})
            except Exception as exc:
                self.json_response(500, {"ok": False, "error": f"获取话题趋势失败：{exc}"})
            return

        if parsed.path == "/":
            self.path = "/index.html"
        elif VUE_DIST.is_dir() and not Path(self.translate_path(self.path)).exists():
            # Vue SPA fallback：非 /api 路径且文件不存在时，返回 index.html
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        logger.info(f"POST {self.path}")
        if not self._check_write_auth():
            self.json_response(403, {"ok": False, "error": "未授权：写接口仅允许本机访问；远程访问需设置 AUTH_TOKEN 环境变量并在请求头携带 Authorization: Bearer <token>。"})
            return
        try:
            body = self.read_json_body()

            if parsed.path == "/api/login/qrcode":
                info = login_qrcode_generate()
                self.json_response(200, {"ok": True, "data": info})
                return

            # 小红书扫码登录 - 生成二维码（API 方式，和 B站一样）
            if parsed.path == "/api/xhs/login/qrcode":
                if xhs_login is None:
                    self.json_response(503, {"ok": False, "error": "服务器未安装 playwright，无法扫码登录"})
                    return
                try:
                    result = xhs_login.create_qrcode()
                    self.json_response(200, {"ok": True, "data": {
                        "url": result["url"],
                        "qr_id": result["qr_id"],
                        "code": result["code"],
                    }})
                except Exception as exc:
                    logger.exception("小红书二维码生成失败")
                    self.json_response(502, {"ok": False, "error": f"生成二维码失败：{exc}"})
                return

            # 小红书扫码登录 - 轮询状态（API 方式，和 B站一样）
            if parsed.path == "/api/xhs/login/poll":
                if xhs_login is None:
                    self.json_response(503, {"ok": False, "error": "服务器未安装 playwright"})
                    return
                qr_id = (body.get("qr_id") or "").strip()
                code = (body.get("code") or "").strip()
                if not qr_id or not code:
                    self.json_response(400, {"ok": False, "error": "缺少 qr_id 或 code"})
                    return
                try:
                    result = xhs_login.poll_qrcode(qr_id, code)
                    resp_data = {"code_status": result["code_status"]}
                    if result["code_status"] == 2 and result.get("cookies"):
                        resp_data["cookies"] = result["cookies"]
                        # 强制让抓取链路重新读取最新 Cookie
                        globals()["SESSION_READY"] = False
                    self.json_response(200, {"ok": True, "data": resp_data})
                except Exception as exc:
                    logger.exception("小红书扫码轮询失败")
                    self.json_response(502, {"ok": False, "error": str(exc)})
                return

            # 小红书 Cookie 保存
            if parsed.path == "/api/xhs/login/cookies":
                a1 = (body.get("a1") or "").strip()
                web_session = (body.get("web_session") or "").strip()
                web_id = (body.get("webId") or "").strip()
                if not a1:
                    self.json_response(400, {"ok": False, "error": "a1 是必填项"})
                    return
                # 写入 cookies_xhs.txt
                try:
                    cookie_file = ROOT / "cookies_xhs.txt"
                    lines = []
                    if a1:
                        lines.append(f"a1={a1}")
                    if web_session:
                        lines.append(f"web_session={web_session}")
                    if web_id:
                        lines.append(f"webId={web_id}")
                    cookie_file.write_text("\n".join(lines), encoding="utf-8")
                    # 清除客户端缓存，下次请求重新读取
                    xhs_client._cookies_cache = None
                    logger.info(f"小红书 Cookie 已保存到 {cookie_file}")
                    self.json_response(200, {"ok": True, "data": {"configured": True}})
                except Exception as exc:
                    self.json_response(500, {"ok": False, "error": f"保存失败：{exc}"})
                return

            if parsed.path == "/api/login/poll":
                qrcode_key = (body.get("qrcodeKey") or "").strip()
                info = login_qrcode_poll(qrcode_key)
                if info.get("code") == 0:
                    # 强制让会话/抓取链路重新读取最新 Cookie
                    globals()["SESSION_READY"] = False
                    bootstrap_session(force=True)
                self.json_response(200, {"ok": True, "data": info})
                return

            if parsed.path == "/api/login/logout":
                try:
                    if COOKIE_FILE.exists():
                        COOKIE_FILE.unlink()
                except Exception as exc:
                    logger.warning(f"删除 cookies.txt 失败：{exc}")
                # 清空内存里的 B站 Cookie
                for c in list(COOKIE_JAR):
                    if "bilibili" in (c.domain or ""):
                        try:
                            COOKIE_JAR.clear(c.domain, c.path, c.name)
                        except Exception:
                            pass
                globals()["SESSION_READY"] = False
                logger.info("B站登录已退出。")
                self.json_response(200, {"ok": True})
                return

            if parsed.path == "/api/xhs/login/logout":
                # 小红书退出登录
                try:
                    xhs_cookie_file = ROOT / "cookies_xhs.txt"
                    if xhs_cookie_file.exists():
                        xhs_cookie_file.unlink()
                except Exception as exc:
                    logger.warning(f"删除 cookies_xhs.txt 失败：{exc}")
                # 清除 xhs_client 的 cookie 缓存
                try:
                    from analysis import xhs_client
                    xhs_client._cookies_cache = None
                except Exception:
                    pass
                logger.info("小红书登录已退出。")
                self.json_response(200, {"ok": True})
                return

            if parsed.path == "/api/config/llm":
                # 保存 LLM 配置到 .env 并热重载模块
                api_key = (body.get("apiKey") or "").strip()
                base_url = (body.get("baseUrl") or "").strip()
                model = (body.get("model") or "").strip()
                timeout = str(body.get("timeout") or "30").strip()

                # apiKey 字段如果以 *** 结尾（掩码），说明用户没改 key，保留原值
                env_map = _read_env_file()
                existing_key = env_map.get("LLM_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
                if api_key and api_key.endswith("***"):
                    # 掩码回显，保留原 key
                    api_key = existing_key
                if not api_key and body.get("clearKey"):
                    # 用户主动清空
                    api_key = ""

                updates = {
                    "LLM_API_KEY": api_key,
                    "LLM_BASE_URL": base_url,
                    "LLM_MODEL": model,
                    "LLM_TIMEOUT": timeout,
                }
                _write_env_file(updates, group_comment="# LLM 配置（由前端设置面板写入）")
                reloaded = _reload_llm_module()
                logger.info(f"LLM 配置已保存，热重载={'成功' if reloaded else '失败或未启用'}")
                self.json_response(200, {
                    "ok": True,
                    "available": bool(_llm_available()),
                    "reloaded": reloaded,
                    "message": "配置已保存并生效" if reloaded else "配置已保存，但 LLM 仍未启用（请检查 API Key）",
                })
                return

            if parsed.path == "/api/config/alert":
                # 保存 Webhook 告警配置到 .env
                webhook_url = (body.get("webhookUrl") or "").strip()
                min_risk = (body.get("minRisk") or "high").strip().lower()
                cooldown = str(body.get("cooldown") or "3600").strip()

                if min_risk not in ("low", "medium", "high"):
                    min_risk = "high"
                try:
                    cooldown_val = max(60, int(cooldown))
                except ValueError:
                    cooldown_val = 3600

                updates = {
                    "ALERT_WEBHOOK_URL": webhook_url,
                    "ALERT_MIN_RISK": min_risk,
                    "ALERT_COOLDOWN_SEC": str(cooldown_val),
                }
                _write_env_file(updates, group_comment="# Webhook 告警配置（由前端设置面板写入）")
                # 同步到 os.environ，让 alert 模块立即生效（alert 模块每次调用都读 os.environ，无需 reload）
                for k, v in updates.items():
                    if v:
                        os.environ[k] = v
                    else:
                        os.environ.pop(k, None)
                # 重置冷却记录，让测试或下次告警能立即触发
                try:
                    from analysis.alert import reset_cooldown
                    reset_cooldown()
                except Exception:
                    pass
                logger.info(f"告警配置已保存：webhook={'已设置' if webhook_url else '未设置'} min_risk={min_risk} cooldown={cooldown_val}s")
                self.json_response(200, {
                    "ok": True,
                    "configured": bool(webhook_url),
                    "message": "告警配置已保存并生效" if webhook_url else "已清空告警配置（不再推送）",
                })
                return

            if parsed.path == "/api/config/alert/test":
                # 发送一条测试告警
                try:
                    from analysis.alert import send_alert, reset_cooldown, _get_webhook_url, _detect_platform
                    webhook_url = _get_webhook_url()
                    if not webhook_url:
                        raise ValueError("未配置 ALERT_WEBHOOK_URL，请先保存 Webhook 地址")
                    reset_cooldown("__test__")
                    ok = send_alert(
                        monitor_id="__test__",
                        risk="high",
                        title="【测试】声浪雷达告警通道验证",
                        text="这是一条测试告警，用于验证 Webhook 配置是否正确。如果你收到了，说明配置成功！",
                        url="",
                    )
                    platform = _detect_platform(webhook_url)
                    self.json_response(200, {
                        "ok": True,
                        "sent": ok,
                        "platform": platform,
                        "message": "测试告警已发送，请检查你的群消息" if ok else "发送失败，请检查 Webhook 地址是否正确",
                    })
                except Exception as exc:
                    self.json_response(200, {"ok": True, "sent": False, "message": f"测试失败：{exc}"})
                return

            if parsed.path == "/api/monitor/add":
                raw_url = (body.get("url") or "").strip()
                if not raw_url:
                    raise ValueError("请填写视频链接。")
                interval_value = max(1, int(body.get("intervalValue") or 1))
                interval_unit = body.get("intervalUnit") if body.get("intervalUnit") in ("小时", "天") else "小时"
                pages = max(1, min(int(body.get("pages") or 5), 20))
                monitor = {
                    "id": uuid4().hex,
                    "url": raw_url,
                    "title": body.get("title") or "等待首次检测",
                    "pages": pages,
                    "intervalValue": interval_value,
                    "intervalUnit": interval_unit,
                    "enabled": bool(body.get("enabled", True)),
                    "status": "pending",
                    "lastRun": "",
                    "lastRunTs": 0,
                    "nextRunTs": now_ts(),
                    "nextRun": "启动后立即检测",
                    "lastError": "",
                    "lastResult": None,
                    "history": [],
                    "createdAt": fmt_ts(),
                    "updatedAt": fmt_ts(),
                }
                data = load_db()
                data.setdefault("monitors", []).insert(0, monitor)
                save_db(data)
                self.json_response(200, {"ok": True, "monitor": public_monitor(monitor)})
                return

            if parsed.path == "/api/monitor/update":
                monitor_id = body.get("id")
                data = load_db()
                monitor = find_monitor(data, monitor_id)
                if not monitor:
                    raise ValueError("监测任务不存在。")
                if "url" in body and str(body["url"]).strip():
                    monitor["url"] = str(body["url"]).strip()
                    monitor["title"] = "等待重新检测"
                if "pages" in body:
                    monitor["pages"] = max(1, min(int(body.get("pages") or 5), 20))
                if "intervalValue" in body:
                    monitor["intervalValue"] = max(1, int(body.get("intervalValue") or 1))
                if "intervalUnit" in body and body.get("intervalUnit") in ("小时", "天"):
                    monitor["intervalUnit"] = body["intervalUnit"]
                if "enabled" in body:
                    monitor["enabled"] = bool(body["enabled"])
                monitor["nextRunTs"] = now_ts() + interval_seconds(monitor.get("intervalValue", 1), monitor.get("intervalUnit", "小时"))
                monitor["nextRun"] = fmt_ts(monitor["nextRunTs"])
                monitor["updatedAt"] = fmt_ts()
                save_db(data)
                self.json_response(200, {"ok": True, "monitor": public_monitor(monitor)})
                return

            if parsed.path == "/api/monitor/delete":
                monitor_id = body.get("id")
                data = load_db()
                before = len(data.get("monitors", []))
                data["monitors"] = [m for m in data.get("monitors", []) if m.get("id") != monitor_id]
                if len(data["monitors"]) == before:
                    raise ValueError("监测任务不存在。")
                save_db(data)
                self.json_response(200, {"ok": True})
                return

            if parsed.path == "/api/monitor/run":
                monitor_id = body.get("id")
                result = run_monitor_once(monitor_id, manual=True)
                self.json_response(200, {"ok": True, "data": result})
                return

            self.json_response(404, {"ok": False, "error": "接口不存在。"})
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            self.json_response(502, {"ok": False, "error": f"网络或平台接口访问失败：{exc}"})
        except Exception as exc:
            self.json_response(400, {"ok": False, "error": str(exc)})


def ensure_python_deps() -> None:
    """启动时自动检测并安装 requirements.txt 中缺失的依赖。"""
    import importlib
    import subprocess
    import sys

    req_file = ROOT / "requirements.txt"
    if not req_file.exists():
        return

    # requirements.txt 中包名 -> 实际 import 名（一般同名）
    import_name_map = {
        "jieba": "jieba",
    }

    try:
        lines = req_file.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        logger.warning(f"读取 requirements.txt 失败：{exc}")
        return

    missing: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 解析 "jieba>=0.42.1" / "jieba==0.42.1" / "jieba"
        pkg_name = re.split(r"[<>=!~\s]", line, maxsplit=1)[0].strip()
        if not pkg_name:
            continue
        import_name = import_name_map.get(pkg_name, pkg_name.replace("-", "_"))
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(line)

    if not missing:
        logger.info("Python 依赖检查通过。")
        return

    logger.info(f"检测到缺失依赖：{missing}，正在自动安装...")
    print(f"[依赖安装] 检测到缺失：{missing}，正在 pip install ...")

    pip_base = [sys.executable, "-m", "pip", "install"]

    def _run_pip(args: list[str]) -> tuple[int, str, str]:
        proc = subprocess.run(
            pip_base + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        return proc.returncode, proc.stdout, proc.stderr

    try:
        # 先优先用 wheel 安装，避免老版本 jieba 走 sdist 编译路径
        code, out, err = _run_pip(["--prefer-binary", "--only-binary=:all:", *missing])
        if code != 0:
            # 如果只有 sdist 可用，先确保 setuptools/wheel 存在再重试
            logger.info("--only-binary 失败，尝试安装 setuptools/wheel 后再回到普通安装。")
            _run_pip(["-U", "setuptools", "wheel"])
            code, out, err = _run_pip(missing)
        if code == 0:
            logger.info("依赖自动安装成功。")
            print("[依赖安装] 成功。")
        else:
            logger.warning(f"pip install 返回非 0：{code}")
            logger.warning(f"stdout: {out[-500:]}")
            logger.warning(f"stderr: {err[-500:]}")
            print(
                f"[依赖安装] 失败，请手动执行： pip install -r {req_file}\n"
                f"错误信息：{err[-300:]}"
            )
    except FileNotFoundError:
        logger.warning("未找到 pip，请确认 Python 环境完整。")
    except subprocess.TimeoutExpired:
        logger.warning("pip install 超时（300秒），请手动安装依赖。")
    except Exception as exc:
        logger.warning(f"自动安装依赖时出错：{exc}")


def build_frontend() -> None:
    """在 server.py 启动时自动构建 Vue 前端。"""
    import subprocess
    import sys

    frontend_dir = ROOT / "frontend"
    if not (frontend_dir / "package.json").exists():
        logger.info("frontend/package.json 不存在，跳过自动构建")
        return

    dist_dir = frontend_dir / "dist"
    # 如果 dist 已存在且不是空目录，跳过构建（加速重启）
    if dist_dir.is_dir() and any(dist_dir.iterdir()):
        logger.info("frontend/dist 已存在，跳过 npm run build（如需强制重建请删除 dist 目录）")
        return

    logger.info("正在构建 Vue 前端，请稍候...")
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(frontend_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("Vue 前端构建成功")
        else:
            logger.warning(f"Vue 前端构建失败（code={result.returncode}），请检查 frontend 目录")
            logger.warning(f"stdout: {result.stdout[-500:]}")
            logger.warning(f"stderr: {result.stderr[-500:]}")
    except FileNotFoundError:
        logger.warning("未找到 npm，请确保 Node.js 已安装并加入 PATH")
    except subprocess.TimeoutExpired:
        logger.warning("npm run build 超时（120秒），跳过构建")
    except Exception as exc:
        logger.warning(f"构建前端时出错：{exc}")


def main() -> None:
    logger.info(f"工作目录：{ROOT}")
    logger.info(f"日志文件：{LOG_FILE}")
    # LLM 报告配置状态
    if _llm_available():
        logger.info(f"LLM 报告已启用：模型={os.environ.get('LLM_MODEL', 'deepseek-chat')} base={os.environ.get('LLM_BASE_URL', 'https://api.deepseek.com/v1')}")
    else:
        logger.warning("LLM 报告未启用：未配置 LLM_API_KEY（参考 .env.example），AI 报告将使用模板降级。")
    ensure_python_deps()  # 启动时自动安装 requirements.txt 中缺失的依赖
    # 如果首次安装了 jieba，重新尝试加载词典模块
    global _LEXICON_OK
    if not _LEXICON_OK:
        try:
            import importlib
            from analysis import lexicon as _lex
            importlib.reload(_lex)
            _LEXICON_OK = True
            logger.info("依赖安装后已重新加载情感词典。")
        except Exception as exc:
            logger.warning(f"重新加载词典失败：{exc}")
    build_frontend()  # 启动时自动构建 Vue 前端
    bootstrap_session()
    threading.Thread(target=scheduler_loop, daemon=True).start()
    # 绑定 0.0.0.0 以支持容器/云部署（Railway/Docker），本地访问 127.0.0.1 仍可用
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    logger.info(f"声浪雷达监测版已启动：http://0.0.0.0:{PORT}")
    print(f"声浪雷达监测版已启动：http://localhost:{PORT}")
    print("按 Ctrl+C 停止服务")
    server.serve_forever()


if __name__ == "__main__":
    main()
