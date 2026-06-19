"""LLM 增强情感分析模块

对词典法判为"中性"的评论，批量交给 LLM 做二次分类。
复用 llm_report.py 的 LLM 通道（OpenAI 兼容协议），零新增依赖。

设计目标：
1. 词典法已有明确判断的评论（pos/neg/risk/con）→ 直接采用，不调 LLM（省 token、省时间）
2. 词典法判为 neu 的评论 → 每 20 条为一批送 LLM 做分类
3. LLM 能理解反讽、阴阳怪气、网络梗，比词典法更准
4. LLM 不可用或调用失败 → 维持词典法中性结果，不影响主流程

配置（与 llm_report.py 共享）：
    LLM_API_KEY    —— 必填，OpenAI 兼容 API key
    LLM_BASE_URL   —— 可选，默认 https://api.deepseek.com/v1
    LLM_MODEL      —— 可选，默认 deepseek-chat
    LLM_TIMEOUT    —— 可选，默认 30 秒

用法：
    from analysis.llm_sentiment import enhance_neutral_comments
    stats = enhance_neutral_comments(comments)  # 原地修改 comment["sentiment"]
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any

logger = logging.getLogger("llm_sentiment")

# 复用 llm_report 的配置（保持单一来源，避免配置漂移）
API_KEY = os.environ.get("LLM_API_KEY", "").strip()
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))

# 每批送入 LLM 的评论数。20 条兼顾 token 消耗和上下文理解。
# DeepSeek-chat 上下文 32K，20 条评论 + prompt 约 3-5K token，余量充足。
BATCH_SIZE = 20

# 有效的情感标签
VALID_LABELS = {"pos", "neg", "neu", "con", "risk"}


def is_available() -> bool:
    """LLM 增强是否可用（已配置 API key）。"""
    return bool(API_KEY)


def enhance_neutral_comments(comments: list[dict[str, Any]]) -> dict[str, int]:
    """对 comments 中 sentiment=="neu" 的评论做 LLM 批量增强。

    原地修改 comment["sentiment"]，同时写入 comment["llm_enhanced"]=True。

    Args:
        comments: 评论列表，每条需有 "text" 和 "sentiment" 字段

    Returns:
        统计 {"total_neutral": N, "enhanced": M, "unchanged": K}
        - total_neutral: 初始为 neu 的评论数
        - enhanced: 被 LLM 重新分类为 pos/neg/con/risk 的数量
        - unchanged: 仍为 neu 的数量（含 LLM 维持判断和调用失败）
    """
    neutral_indices = [
        i for i, c in enumerate(comments) if c.get("sentiment") == "neu"
    ]
    total_neutral = len(neutral_indices)

    # 无中性评论或 LLM 不可用 → 直接返回
    if total_neutral == 0 or not is_available():
        logger.debug(
            f"LLM 增强跳过：neutral={total_neutral}, available={is_available()}"
        )
        return {
            "total_neutral": total_neutral,
            "enhanced": 0,
            "unchanged": total_neutral,
        }

    enhanced = 0
    failed_batches = 0

    # 分批处理，每批 BATCH_SIZE 条
    for batch_start in range(0, total_neutral, BATCH_SIZE):
        batch_indices = neutral_indices[batch_start : batch_start + BATCH_SIZE]
        batch_items = [
            (i, str(comments[i].get("text", ""))[:200]) for i in batch_indices
        ]

        try:
            labels = _classify_batch(batch_items)
            for idx, label in labels.items():
                if label in VALID_LABELS:
                    comments[idx]["sentiment"] = label
                    comments[idx]["llm_enhanced"] = True
                    if label != "neu":
                        enhanced += 1
        except Exception as exc:
            failed_batches += 1
            logger.warning(
                f"LLM 批量分类失败（batch {batch_start}-{batch_start+len(batch_indices)}）：{exc}"
            )

    logger.info(
        f"LLM 情感增强完成：{total_neutral} 条中性评论 → {enhanced} 条重新分类，"
        f"{failed_batches} 批失败"
    )
    return {
        "total_neutral": total_neutral,
        "enhanced": enhanced,
        "unchanged": total_neutral - enhanced,
    }


def _classify_batch(items: list[tuple[int, str]]) -> dict[int, str]:
    """调用 LLM 对一批评论做情感分类。

    Args:
        items: [(comment_index, comment_text), ...]

    Returns:
        {comment_index: "pos|neg|neu|con|risk"}
    """
    # 构造评论列表文本
    lines = []
    for idx, text in items:
        # 转义双引号，避免破坏 JSON
        safe_text = text.replace('"', "'").replace("\n", " ")
        lines.append(f'[{idx}] "{safe_text}"')
    comments_block = "\n".join(lines)

    prompt = f"""你是中文情感分析专家。请对以下 B站评论逐条做情感分类。

评论列表：
{comments_block}

分类标签（每条评论选一个）：
- pos：正面（赞美、支持、喜欢、学到东西、感动等）
- neg：负面（批评、不满、失望、无聊、嘲讽等）
- neu：中性（陈述事实、无关内容、无明确倾向）
- con：争议（引发争论、对立观点、引战）
- risk：风险（侮辱、人身攻击、违规、极端言论）

注意：
1. 理解中文语境，包括反讽、阴阳怪气、网络梗
2. 如果确实无法判断倾向，保持 neu
3. 只输出 JSON 对象，不要任何前后缀文字

输出格式（严格 JSON 对象）：
{{"results": [{{"id": 0, "label": "pos"}}, {{"id": 1, "label": "neg"}}]}}"""

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是中文情感分析专家，擅长理解网络评论语境。只输出 JSON。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,  # 分类任务用低温度保证稳定性
        "max_tokens": 1500,
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

    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data["choices"][0]["message"]["content"]
    logger.info(
        f"LLM 批量分类成功：{len(items)} 条评论，响应 {len(content)} 字符"
    )

    return _parse_labels(content)


def _parse_labels(content: str) -> dict[int, str]:
    """解析 LLM 返回的 JSON，提取 {id: label} 映射。

    兼容：
    - DeepSeek-R1 / QwQ 等推理模型的 <think>...</think> 思维链
    - 未闭合的 <think> 标签
    - markdown 代码块标记
    - 直接数组 vs {"results": [...]} 两种结构
    """
    if not content:
        return {}

    text = content.strip()

    # 1. 剥离 <think>...</think> 思维链（推理模型）
    think_start = text.find("<think>")
    if think_start >= 0:
        think_end = text.find("</think>", think_start)
        if think_end >= 0:
            # 闭合：保留 <think> 之前 + </think> 之后
            text = (
                text[:think_start] + text[think_end + len("</think>") :]
            ).strip()
        else:
            # 未闭合：<think> 到结尾全是思维链，但答案 JSON 可能在思维链末尾
            text = text[think_start + len("<think>") :].strip()

    # 2. 去除可能的 markdown 代码块标记
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 3. 尝试解析 JSON
    obj: Any = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # 4. 兜底：正则提取 JSON 对象或数组
        # 先尝试 {...}
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group())
            except json.JSONDecodeError:
                pass
        if obj is None:
            # 再尝试 [...]
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if match:
                try:
                    obj = {"results": json.loads(match.group())}
                except json.JSONDecodeError:
                    pass

    if obj is None:
        logger.warning(f"LLM 标签解析失败，原始前200字：{content[:200]}")
        return {}

    # 统一为 list 结构
    items = obj.get("results", obj) if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        return {}

    labels: dict[int, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("id")
        label = str(item.get("label", "neu")).lower().strip()
        if isinstance(idx, int) and idx >= 0 and label in VALID_LABELS:
            labels[idx] = label
    return labels
