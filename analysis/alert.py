"""Webhook 告警模块

监测任务检测到 high 风险等级时，通过 Webhook 推送告警到飞书/钉钉/企业微信。
当 risk >= medium 时，先经 LLM 二次判定，减少误报。

环境变量：
    ALERT_WEBHOOK_URL   Webhook 地址（未设置则不告警）
    ALERT_MIN_RISK      触发告警的最低风险等级，默认 "high"
    ALERT_COOLDOWN_SEC  同一任务告警冷却时间（秒），默认 3600（1 小时）
    LLM_API_KEY         LLM API key（复用 llm_report 配置）
    LLM_BASE_URL        LLM 基础 URL（复用 llm_report 配置）
    LLM_MODEL           LLM 模型名（复用 llm_report 配置）
    LLM_TIMEOUT         LLM 超时（复用 llm_report 配置）

支持的 Webhook 格式：
    - 飞书：自动发送 interactive 卡片消息
    - 钉钉：自动发送 markdown 消息
    - 企业微信：自动发送 markdown 消息
    - 通用：发送 JSON {text, title, url, risk, video}

通过 URL 关键字自动识别平台：
    - 包含 "feishu" 或 "larksuite" → 飞书
    - 包含 "dingtalk" → 钉钉
    - 包含 "qyapi.weixin" → 企业微信
    - 其他 → 通用 JSON
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("alert")

# 模块级冷却记录：{monitor_id: last_alert_ts}
_last_alert: dict[str, float] = {}

# 风险等级权重，用于比较
_RISK_WEIGHT = {"unknown": 0, "low": 1, "medium": 2, "high": 3}


def _get_webhook_url() -> str:
    return os.environ.get("ALERT_WEBHOOK_URL", "").strip()


def _get_min_risk() -> str:
    return os.environ.get("ALERT_MIN_RISK", "high").strip().lower()


def _get_cooldown() -> int:
    try:
        return max(60, int(os.environ.get("ALERT_COOLDOWN_SEC", "3600")))
    except ValueError:
        return 3600


def _get_llm_config() -> tuple[str, str, str, int]:
    """获取 LLM 配置，复用 llm_report 的环境变量。"""
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    base_url = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    try:
        timeout = int(os.environ.get("LLM_TIMEOUT", "30"))
    except ValueError:
        timeout = 30
    return api_key, base_url, model, timeout


def _llm_judge(
    risk: str,
    sentiments: dict[str, float],
    keywords: list[str],
    top_neg_comments: list[str],
    history_baseline: dict[str, float] | None,
    title: str = "",
) -> dict[str, Any] | None:
    """LLM 二次判定：判断本次数据变化是否真的值得告警。

    Args:
        risk: 当前风险等级（low/medium/high）
        sentiments: 本次情绪分布百分比 {"pos": 55.0, "neg": 15.0, ...}
        keywords: 本次高频关键词
        top_neg_comments: 本次 top 负面评论原文
        history_baseline: 历史均值 {"pos": 60.0, "neg": 10.0, ...}，无历史时为 None
        title: 视频标题

    Returns:
        成功返回 {"should_alert": bool, "reason": str, "urgency": "low|medium|high"}
        失败返回 None（降级回固定阈值）
    """
    api_key, base_url, model, timeout = _get_llm_config()
    if not api_key:
        logger.info("LLM 未配置 API key，跳过二次判定")
        return None

    # 构造对比数据描述
    baseline_str = "无历史数据"
    if history_baseline:
        baseline_str = (
            f"正向 {history_baseline.get('pos', 0):.1f}%、"
            f"中性 {history_baseline.get('neu', 0):.1f}%、"
            f"负向 {history_baseline.get('neg', 0):.1f}%、"
            f"争议 {history_baseline.get('con', 0):.1f}%、"
            f"风险 {history_baseline.get('risk', 0):.1f}%"
        )

    current_str = (
        f"正向 {sentiments.get('pos', 0):.1f}%、"
        f"中性 {sentiments.get('neu', 0):.1f}%、"
        f"负向 {sentiments.get('neg', 0):.1f}%、"
        f"争议 {sentiments.get('con', 0):.1f}%、"
        f"风险 {sentiments.get('risk', 0):.1f}%"
    )

    neg_samples = "\n".join(f"  - {c[:100]}" for c in top_neg_comments[:5]) if top_neg_comments else "  （无）"
    kw_str = "、".join(keywords[:10]) if keywords else "无"

    prompt = f"""你是舆情监测系统的告警判定助手。请判断以下数据变化是否值得触发告警。

## 视频标题
{title or "未命名视频"}

## 当前风险等级
{risk}

## 本次情绪分布（百分比）
{current_str}

## 历史情绪均值（百分比）
{baseline_str}

## 本次高频关键词
{kw_str}

## 本次典型负面/风险评论
{neg_samples}

---

请判断：这次的情绪变化和负面评论，是真的出现了需要关注的舆情风险，还是正常的日常波动？

判断依据：
1. 负面/风险比例是否相比历史基线显著上升（>10个百分点）
2. 负面评论是否集中指向某个具体问题（而非零散吐槽）
3. 关键词是否出现新的负面话题
4. 综合判断是否需要人工介入

请输出严格 JSON（不要 markdown 代码块标记）：
{{"should_alert": true或false, "reason": "判断理由，1-2句话", "urgency": "low或medium或high"}}"""

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是舆情监测告警判定助手。根据数据变化判断是否需要告警。输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        import urllib.request as _urllib_request
        import urllib.error as _urllib_error

        with _urllib_request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        logger.info(f"LLM 二次判定完成，响应 {len(content)} 字符")

        # 解析 JSON（兼容思维链模型）
        result = _parse_judge_json(content)
        if result and "should_alert" in result:
            logger.info(
                f"LLM 判定结果：should_alert={result['should_alert']} "
                f"urgency={result.get('urgency')} reason={result.get('reason', '')[:80]}"
            )
            return result
        logger.warning(f"LLM 判定 JSON 缺少 should_alert 字段：{content[:200]}")
        return None
    except Exception as exc:
        logger.warning(f"LLM 二次判定失败，降级回固定阈值：{exc}")
        return None


def _parse_judge_json(content: str) -> dict[str, Any] | None:
    """解析 LLM 判定返回的 JSON，兼容思维链模型。"""
    import re

    text = content.strip()

    # 剥离 ewise...🦉 思维链
    think_start = text.find("ewise")
    if think_start < 0:
        think_start = text.find("\U0001f916")
    if think_start < 0:
        think_start = text.find("🤖")
    if think_start >= 0:
        think_end = text.find("\U0001f4a4", think_start)
        if think_end < 0:
            think_end = text.find("💭", think_start)
        if think_end >= 0:
            text = (text[:think_start] + text[think_end + 1:]).strip()

    # 去除 markdown 代码块标记
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 尝试直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "should_alert" in obj:
            return obj
    except json.JSONDecodeError:
        pass

    # 提取最后一个 {...}
    last_end = text.rfind("}")
    if last_end < 0:
        return None
    depth = 0
    start_idx = -1
    in_string = False
    for i in range(last_end, -1, -1):
        ch = text[i]
        if ch == '}' and not in_string:
            depth += 1
        elif ch == '{' and not in_string:
            depth -= 1
            if depth == 0:
                start_idx = i
                break
        elif ch == '"':
            in_string = not in_string
    if start_idx >= 0:
        try:
            obj = json.loads(text[start_idx:last_end + 1])
            if isinstance(obj, dict) and "should_alert" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    # 正则兜底
    candidates = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
    for c in reversed(candidates):
        try:
            obj = json.loads(c)
            if isinstance(obj, dict) and "should_alert" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _detect_platform(url: str) -> str:
    """根据 URL 自动识别 Webhook 平台。"""
    u = url.lower()
    if "feishu" in u or "larksuite" in u:
        return "feishu"
    if "dingtalk" in u or "oapi.dingtalk" in u:
        return "dingtalk"
    if "qyapi.weixin" in u:
        return "wecom"
    return "generic"


def _build_feishu_card(payload: dict[str, Any]) -> dict[str, Any]:
    """飞书互动卡片消息。"""
    risk = payload.get("risk", "unknown")
    title = payload.get("title", "未命名视频")
    text = payload.get("text", "")
    video_url = payload.get("url", "")
    risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk, "⚪")
    header_color = {"high": "red", "medium": "yellow", "low": "green"}.get(risk, "grey")

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{risk_emoji} 风险等级：{risk.upper()}**"},
        },
        {"tag": "hr"},
        {"tag": "div", "text": {"tag": "lark_md", "content": f"**视频：** {title}"}},
    ]
    if text:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**分析：** {text}"}})
    if video_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看视频"},
                "url": video_url,
                "type": "primary",
            }],
        })

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "📢 声浪雷达 · 舆情告警"},
                "template": header_color,
            },
            "elements": elements,
        },
    }


def _build_dingtalk_markdown(payload: dict[str, Any]) -> dict[str, Any]:
    """钉钉 markdown 消息。"""
    risk = payload.get("risk", "unknown")
    title = payload.get("title", "未命名视频")
    text = payload.get("text", "")
    video_url = payload.get("url", "")
    risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk, "⚪")

    lines = [
        f"### {risk_emoji} 声浪雷达 · 舆情告警",
        f"**风险等级：** {risk.upper()}",
        f"**视频：** [{title}]({video_url})" if video_url else f"**视频：** {title}",
    ]
    if text:
        lines.append(f"**分析：** {text}")
    return {
        "msgtype": "markdown",
        "markdown": {"title": "声浪雷达告警", "text": "\n\n".join(lines)},
    }


def _build_wecom_markdown(payload: dict[str, Any]) -> dict[str, Any]:
    """企业微信 markdown 消息。"""
    risk = payload.get("risk", "unknown")
    title = payload.get("title", "未命名视频")
    text = payload.get("text", "")
    video_url = payload.get("url", "")
    risk_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(risk, "⚪")

    lines = [
        f"{risk_emoji} **声浪雷达 · 舆情告警**",
        f"风险等级：<font color=\"warning\">{risk.upper()}</font>",
        f"视频：{title}",
    ]
    if text:
        lines.append(f"分析：{text}")
    if video_url:
        lines.append(f"[查看视频]({video_url})")
    return {"msgtype": "markdown", "markdown": {"content": "\n".join(lines)}}


def _build_generic_json(payload: dict[str, Any]) -> dict[str, Any]:
    """通用 JSON 消息（自定义接收方）。"""
    return {
        "source": "shenglang-radar",
        "event": "risk_alert",
        "risk": payload.get("risk"),
        "title": payload.get("title"),
        "text": payload.get("text"),
        "url": payload.get("url"),
        "timestamp": int(time.time()),
    }


def _build_message(payload: dict[str, Any], platform: str) -> dict[str, Any]:
    """根据平台构造对应格式的消息体。"""
    if platform == "feishu":
        return _build_feishu_card(payload)
    if platform == "dingtalk":
        return _build_dingtalk_markdown(payload)
    if platform == "wecom":
        return _build_wecom_markdown(payload)
    return _build_generic_json(payload)


def _send_webhook(url: str, body: dict[str, Any]) -> bool:
    """发送 Webhook 请求，返回是否成功。"""
    try:
        import urllib.request
        import urllib.error

        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            resp_body = resp.read().decode("utf-8", errors="replace")
            if 200 <= status < 300:
                logger.info(f"Webhook 告警发送成功 status={status}")
                return True
            logger.warning(f"Webhook 返回非 2xx status={status} body={resp_body[:200]}")
            return False
    except urllib.error.URLError as e:
        logger.warning(f"Webhook 发送失败（网络）：{e}")
        return False
    except Exception as e:
        logger.warning(f"Webhook 发送异常：{e}")
        return False


def should_alert(monitor_id: str, risk: str) -> bool:
    """判断是否应触发告警（含冷却判断）。"""
    url = _get_webhook_url()
    if not url:
        return False

    min_risk = _get_min_risk()
    if _RISK_WEIGHT.get(risk, 0) < _RISK_WEIGHT.get(min_risk, 3):
        return False

    # 冷却检查
    cooldown = _get_cooldown()
    now = time.time()
    last = _last_alert.get(monitor_id, 0)
    if now - last < cooldown:
        return False

    return True


def send_alert(
    monitor_id: str,
    risk: str,
    title: str,
    text: str = "",
    url: str = "",
    sentiments: dict[str, float] | None = None,
    keywords: list[str] | None = None,
    top_neg_comments: list[str] | None = None,
    history_baseline: dict[str, float] | None = None,
) -> bool:
    """触发一次告警。

    当 risk >= medium 时，先经 LLM 二次判定，减少误报。
    LLM 不可用时降级回原来的固定阈值逻辑。

    Args:
        monitor_id: 监测任务 ID
        risk: 风险等级（low/medium/high/unknown）
        title: 视频标题
        text: 告警正文（分析摘要或风险原因）
        url: 视频链接
        sentiments: 本次情绪分布百分比 {"pos": 55.0, "neg": 15.0, ...}
        keywords: 本次高频关键词
        top_neg_comments: 本次 top 负面评论原文
        history_baseline: 历史均值 {"pos": 60.0, "neg": 10.0, ...}

    Returns:
        True 表示已发送（且通过 should_alert 判断）；False 表示被跳过或发送失败。
    """
    # === LLM 二次判定（risk >= medium 时触发） ===
    _medium_weight = _RISK_WEIGHT.get("medium", 2)
    if _RISK_WEIGHT.get(risk, 0) >= _medium_weight:
        # 有 sentiments 数据才走 LLM 判定
        if sentiments and keywords is not None:
            judge = _llm_judge(
                risk=risk,
                sentiments=sentiments,
                keywords=keywords,
                top_neg_comments=top_neg_comments or [],
                history_baseline=history_baseline,
                title=title,
            )
            if judge is not None:
                if not judge.get("should_alert", False):
                    logger.info(
                        f"LLM 二次判定不告警 monitor={monitor_id} "
                        f"risk={risk} reason={judge.get('reason', '')[:80]}"
                    )
                    return False
                # LLM 认为需要告警，追加 reason 到正文
                llm_reason = judge.get("reason", "")
                if llm_reason:
                    text = f"{text}\n\n🤖 AI 判定：{llm_reason}" if text else f"🤖 AI 判定：{llm_reason}"
                # 可用 LLM 返回的 urgency 覆盖 risk（如果更精确）
                llm_urgency = judge.get("urgency", "")
                if llm_urgency in _RISK_WEIGHT:
                    risk = llm_urgency
                    logger.info(f"LLM 调整风险等级为 {risk}")
        else:
            logger.info(f"缺少 sentiments/keywords，跳过 LLM 二次判定，使用固定阈值")

    if not should_alert(monitor_id, risk):
        return False

    webhook_url = _get_webhook_url()
    platform = _detect_platform(webhook_url)
    payload = {"risk": risk, "title": title, "text": text, "url": url}
    body = _build_message(payload, platform)

    ok = _send_webhook(webhook_url, body)
    if ok:
        _last_alert[monitor_id] = time.time()
        logger.info(f"告警已触发 monitor={monitor_id} risk={risk} platform={platform}")
    return ok


def reset_cooldown(monitor_id: str | None = None) -> None:
    """重置冷却记录（测试或手动触发用）。"""
    if monitor_id:
        _last_alert.pop(monitor_id, None)
    else:
        _last_alert.clear()
