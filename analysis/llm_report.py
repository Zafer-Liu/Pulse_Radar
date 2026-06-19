"""LLM 舆情报告生成模块

同步调用 LLM（OpenAI 兼容协议，默认 DeepSeek）生成结构化舆情分析报告。
无 API key 或调用失败时，自动降级为模板报告。

配置（环境变量）：
    LLM_API_KEY    —— 必填，OpenAI 兼容 API key
    LLM_BASE_URL   —— 可选，默认 https://api.deepseek.com/v1
    LLM_MODEL      —— 可选，默认 deepseek-chat
    LLM_TIMEOUT    —— 可选，默认 30 秒

输出结构（与 server.py 原 make_report 兼容）：
    {
        "summary": str,          # 整体判断
        "positive": [str],       # 主要正面反馈（3-5 条）
        "negative": [str],       # 主要负面反馈（3-5 条）
        "controversy": str,      # 争议焦点
        "suggestion": str,       # 建议回应策略
        "ai_generated": bool,    # 是否由 LLM 生成
        "model": str,            # 使用的模型名
    }
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

logger = logging.getLogger("llm_report")

# === 配置 ===
API_KEY = os.environ.get("LLM_API_KEY", "").strip()
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))


def is_available() -> bool:
    """LLM 是否可用（已配置 API key）。"""
    return bool(API_KEY)


def _build_prompt(video: dict[str, Any], comments: list[dict[str, Any]],
                  dist: dict[str, int], keywords: list[str],
                  clusters: list[dict[str, Any]] | None = None) -> str:
    """构造喂给 LLM 的结构化摘要 prompt。

    策略：只喂结构化摘要（标题/UP主/情绪分布/TF-IDF关键词/聚类话题/top高赞评论），
    而非全量评论原文。省 token、归纳质量好。
    """
    title = video.get("title", "该视频")
    author = video.get("owner", {}).get("name", "未知")
    total = len(comments)

    # 情绪分布
    pos_n = dist.get("pos", 0)
    neg_n = dist.get("neg", 0)
    neu_n = dist.get("neu", 0)
    risk_n = dist.get("risk", 0)
    con_n = dist.get("con", 0)

    # 关键词
    kw_str = "、".join(keywords[:8]) if keywords else "无"

    # 聚类话题
    cluster_lines = []
    if clusters:
        for c in clusters[:5]:
            cluster_lines.append(
                f"  - {c.get('topic', '未知')}（{c.get('size', 0)}条，主导情绪:{c.get('sentiment', 'neu')}）"
            )
    cluster_str = "\n".join(cluster_lines) if cluster_lines else "  无明显话题聚类"

    # top 高赞评论（正/负/风险各取几条）
    pos_items = [c["text"] for c in comments if c.get("sentiment") == "pos"][:5]
    neg_items = [c["text"] for c in comments if c.get("sentiment") in ("neg", "risk")][:5]
    con_items = [c["text"] for c in comments if c.get("sentiment") == "con"][:3]

    def fmt_list(items: list[str], limit: int = 80) -> str:
        if not items:
            return "  （无）"
        return "\n".join(f"  {i+1}. {t[:limit]}{'…' if len(t) > limit else ''}" for i, t in enumerate(items))

    prompt = f"""你是专业的舆情分析师。请基于以下 B 站视频评论的结构化分析数据，生成一份舆情分析报告。

## 视频信息
- 标题：{title}
- UP主：{author}
- 分析评论数：{total}

## 情绪分布
- 正向 {pos_n} 条 / 中性 {neu_n} 条 / 负向 {neg_n} 条 / 争议 {con_n} 条 / 风险 {risk_n} 条

## TF-IDF 高频关键词
{kw_str}

## 话题聚类
{cluster_str}

## 典型正向评论
{fmt_list(pos_items)}

## 典型负面/风险评论
{fmt_list(neg_items)}

## 典型争议评论
{fmt_list(con_items)}

---

请输出严格的 JSON（不要 markdown 代码块标记），结构如下：
{{
  "summary": "整体舆情判断，2-4 句话，点明情绪基调、核心关注点和潜在风险",
  "positive": ["正面反馈要点1", "正面反馈要点2", "正面反馈要点3"],
  "negative": ["负面反馈要点1", "负面反馈要点2", "负面反馈要点3"],
  "controversy": "争议焦点分析，1-2 句话",
  "suggestion": "建议回应策略，1-2 句话，针对 UP主或运营方"
}}

要求：
1. summary 要结合情绪数据比例和实际评论内容，不要空泛
2. positive/negative 每条 10-30 字，提炼要点而非照搬原文
3. 如果某类评论为空，对应数组填 ["未识别到明显该类反馈"]
4. suggestion 要具体可执行，不要套话
5. 只输出 JSON，不要任何前后缀文字"""
    return prompt


def _call_llm(prompt: str) -> str | None:
    """调用 OpenAI 兼容 API，返回文本响应。失败返回 None。"""
    if not API_KEY:
        return None
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是专业的舆情分析师，擅长从评论数据中提炼洞察。输出严格 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        logger.info(f"LLM 调用成功，模型={MODEL}，响应 {len(content)} 字符")
        return content
    except Exception as exc:
        logger.warning(f"LLM 调用失败，将降级为模板报告：{exc}")
        return None


def _parse_llm_json(content: str) -> dict[str, Any] | None:
    """解析 LLM 返回的 JSON。

    兼容：
    - DeepSeek-R1 / QwQ 等推理模型的 <think>...</think> 思维链
    - 未闭合的 <think> 标签（思维链到文本末尾）
    - markdown 代码块标记
    - 思维链中的伪 JSON 对象（通过深度匹配提取最后一个有效 JSON）
    """
    if not content:
        return None
    text = content.strip()

    # 1. 剥离 <think>...</think> 思维链（推理模型）
    think_start = text.find("<think>")
    if think_start >= 0:
        think_end = text.find("</think>", think_start)
        if think_end >= 0:
            # 闭合：保留 <think> 之前 + </think> 之后
            text = (text[:think_start] + text[think_end + len("</think>"):]).strip()
        else:
            # 未闭合：<think> 到结尾全是思维链，但答案 JSON 可能在思维链末尾
            # 取 <think> 之后内容作为候选（思维链里讨论的 JSON 通常无效）
            text = text[think_start + len("<think>"):].strip()

    # 2. 去除可能的 markdown 代码块标记
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 3. 尝试直接解析
    obj: dict[str, Any] | None = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # 4. 提取最后一个完整的 {...} 块（思维链后真正答案，避开思维链中的伪 JSON）
        #    从右往左找 }，再用深度匹配找对应的 {
        last_end = text.rfind("}")
        if last_end < 0:
            logger.warning(f"LLM JSON 解析失败，无 }} 字符。原始前200字：{content[:200]}")
            return None
        depth = 0
        start_idx = -1
        in_string = False
        escape = False
        # 从 last_end 往左扫描，正确处理字符串内的 { } 避免误判
        for i in range(last_end, -1, -1):
            ch = text[i]
            if escape:
                escape = False
                continue
            # 反向扫描时转义符的判定：如果当前字符是 \，看它前面有几个连续的 \
            # 简化处理：仅在非字符串状态下做深度匹配
            if ch == '}' and not in_string:
                depth += 1
            elif ch == '{' and not in_string:
                depth -= 1
                if depth == 0:
                    start_idx = i
                    break
            elif ch == '"' and not escape:
                # 粗略字符串状态切换（正向语义下 \\" 是转义，反向扫描时此判定不精确，但够用）
                in_string = not in_string
            elif ch == '\\':
                escape = True
        if start_idx < 0:
            logger.warning(f"LLM JSON 解析失败，找不到匹配的 {{。原始前200字：{content[:200]}")
            return None
        candidate = text[start_idx:last_end + 1]
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            # 5. 最后兜底：正则找所有 {...}，从后往前试解析
            import re
            candidates = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
            for c in reversed(candidates):
                try:
                    obj = json.loads(c)
                    break
                except json.JSONDecodeError:
                    continue
            if obj is None:
                logger.warning(f"LLM JSON 解析失败，所有候选无效。原始前200字：{content[:200]}")
                return None

    # 字段校验 + 填充
    result = {
        "summary": str(obj.get("summary", "")).strip(),
        "positive": [str(x) for x in obj.get("positive", [])] or ["未识别到明显正向反馈"],
        "negative": [str(x) for x in obj.get("negative", [])] or ["未识别到明显负面反馈"],
        "controversy": str(obj.get("controversy", "")).strip(),
        "suggestion": str(obj.get("suggestion", "")).strip(),
    }
    if not result["summary"]:
        return None
    return result


def _template_report(video: dict[str, Any], comments: list[dict[str, Any]],
                     dist: dict[str, int], keywords: list[str]) -> dict[str, Any]:
    """模板报告（降级路径，与原 make_report 逻辑一致）。"""
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


def generate_report(video: dict[str, Any], comments: list[dict[str, Any]],
                    dist: dict[str, int], keywords: list[str],
                    clusters: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """生成舆情报告。优先 Agent 模式，其次单次 LLM，最后降级模板。

    与 server.py 原 make_report 签名兼容（多一个 clusters 参数）。

    降级链：Agent（多轮推理） -> 单次 LLM -> 模板报告
    """
    # 无 API key -> 直接模板
    if not API_KEY:
        return _template_report(video, comments, dist, keywords)

    # 评论为空 -> 直接模板（LLM 无米下锅）
    if not comments:
        return _template_report(video, comments, dist, keywords)

    # === 优先 Agent 模式 ===
    try:
        from analysis.agent_core import run as agent_run
        if is_available():
            result = agent_run(video, comments, dist, keywords, clusters)
            if result and result.get("summary"):
                logger.info("Agent 模式报告生成成功")
                return result
            logger.info("Agent 模式未返回有效结果，降级为单次 LLM")
    except Exception as exc:
        logger.warning(f"Agent 模式失败，降级为单次 LLM：{exc}")

    # === 单次 LLM 逻辑 ===
    # 构造 prompt + 调用 LLM
    prompt = _build_prompt(video, comments, dist, keywords, clusters)
    logger.info(f"LLM prompt 构造完成，{len(prompt)} 字符")
    content = _call_llm(prompt)

    if content:
        parsed = _parse_llm_json(content)
        if parsed:
            parsed["ai_generated"] = True
            parsed["model"] = MODEL
            logger.info("LLM 报告生成成功")
            return parsed

    # 降级
    logger.info("LLM 不可用或解析失败，降级为模板报告")
    return _template_report(video, comments, dist, keywords)
