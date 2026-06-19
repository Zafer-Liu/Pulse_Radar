"""Agent 核心模块 -- 最小 ReAct 循环

让 LLM 自主决定调用工具查证数据，多轮推理后生成最终报告。
不依赖 LangChain，纯 Python + OpenAI function calling 实现。

工具：
    search_comments  -- 按情感/关键词搜索评论
    reclassify      -- 修正评论情感标签
    get_trend       -- 获取情绪趋势
    get_cluster_detail -- 获取聚类详情

降级链：Agent 失败 -> 单次 LLM -> 模板报告
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger("agent_core")

# === 复用 llm_report 的 LLM 配置 ===
API_KEY = os.environ.get("LLM_API_KEY", "").strip()
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "30"))

# Agent 专用超时（多轮对话可能更久）
AGENT_TIMEOUT = int(os.environ.get("LLM_AGENT_TIMEOUT", "60"))

# 最大轮数
MAX_ROUNDS_DEFAULT = 5


# === 工具定义（OpenAI function calling 格式） ===

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_comments",
            "description": "按情感标签或关键词搜索评论原文，用于查证特定观点或发现误判。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sentiment": {
                        "type": "string",
                        "enum": ["pos", "neu", "neg", "con", "risk"],
                        "description": "按情感标签过滤，留空则搜索全部",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "按关键词搜索评论内容（模糊匹配）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回条数上限，默认 5",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reclassify",
            "description": "修正评论的情感标签。当你发现某条评论被错误分类时（如反讽被标为正向），调用此工具修正。",
            "parameters": {
                "type": "object",
                "properties": {
                    "comment_indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要修正的评论索引列表（基于原始评论列表）",
                    },
                    "new_label": {
                        "type": "string",
                        "enum": ["pos", "neu", "neg", "con", "risk"],
                        "description": "修正后的情感标签",
                    },
                },
                "required": ["comment_indices", "new_label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trend",
            "description": "获取当前情绪分布的概览和趋势描述，帮助判断整体舆情走向。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cluster_detail",
            "description": "获取指定话题聚类的详细信息，包括该聚类下的代表性评论。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster_index": {
                        "type": "integer",
                        "description": "聚类索引（从 0 开始）",
                    },
                },
                "required": ["cluster_index"],
            },
        },
    },
]


def _call_llm_with_tools(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """调用 OpenAI 兼容 API（支持 function calling），返回完整响应。"""
    if not API_KEY:
        return None

    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 2000,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

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
        with urllib.request.urlopen(req, timeout=AGENT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        logger.debug(f"Agent LLM 调用成功，finish_reason={data['choices'][0].get('finish_reason')}")
        return data
    except Exception as exc:
        logger.warning(f"Agent LLM 调用失败：{exc}")
        return None


def _build_initial_context(
    video: dict[str, Any],
    comments: list[dict[str, Any]],
    dist: dict[str, int],
    keywords: list[str],
    clusters: list[dict[str, Any]] | None,
) -> str:
    """构造 Agent 的初始上下文摘要。"""
    title = video.get("title", "该视频")
    author = video.get("owner", {}).get("name", "未知")
    total = len(comments)

    # 情绪分布
    pos_n = dist.get("pos", 0)
    neg_n = dist.get("neg", 0)
    neu_n = dist.get("neu", 0)
    risk_n = dist.get("risk", 0)
    con_n = dist.get("con", 0)
    total_n = max(total, 1)

    # 百分比
    pos_pct = round(pos_n / total_n * 100, 1)
    neg_pct = round(neg_n / total_n * 100, 1)
    neu_pct = round(neu_n / total_n * 100, 1)
    risk_pct = round(risk_n / total_n * 100, 1)
    con_pct = round(con_n / total_n * 100, 1)

    kw_str = "、".join(keywords[:10]) if keywords else "无"

    # 聚类概览
    cluster_lines = []
    if clusters:
        for i, c in enumerate(clusters[:5]):
            cluster_lines.append(
                f"  [{i}] {c.get('topic', '未知')}（{c.get('size', 0)}条，主导情绪:{c.get('sentiment', 'neu')}）"
            )
    cluster_str = "\n".join(cluster_lines) if cluster_lines else "  无明显话题聚类"

    # top 评论样本
    pos_items = [c["text"] for c in comments if c.get("sentiment") == "pos"][:3]
    neg_items = [c["text"] for c in comments if c.get("sentiment") in ("neg", "risk")][:3]

    def fmt(items: list[str], limit: int = 60) -> str:
        if not items:
            return "  （无）"
        return "\n".join(f"  [{comments.index(next(c for c in comments if c['text'] == t))}] {t[:limit]}{'...' if len(t) > limit else ''}" for t in items)

    context = f"""## 视频信息
- 标题：{title}
- UP主：{author}
- 分析评论数：{total}

## 情绪分布
- 正向 {pos_n} 条（{pos_pct}%）/ 中性 {neu_n} 条（{neu_pct}%）/ 负向 {neg_n} 条（{neg_pct}%）/ 争议 {con_n} 条（{con_pct}%）/ 风险 {risk_n} 条（{risk_pct}%）

## 高频关键词
{kw_str}

## 话题聚类
{cluster_str}

## 典型正向评论（含索引）
{fmt(pos_items)}

## 典型负面/风险评论（含索引）
{fmt(neg_items)}"""
    return context


# === 工具执行函数 ===

def _tool_search_comments(
    comments: list[dict[str, Any]],
    sentiment: str | None,
    keyword: str | None,
    limit: int,
) -> str:
    """执行 search_comments 工具。"""
    results = []
    for i, c in enumerate(comments):
        if len(results) >= limit:
            break
        # 情感过滤
        if sentiment and c.get("sentiment") != sentiment:
            continue
        # 关键词过滤
        if keyword and keyword.lower() not in c.get("text", "").lower():
            continue
        results.append(f"[{i}] [{c.get('sentiment', '?')}] {c['text'][:80]}{'...' if len(c.get('text', '')) > 80 else ''}")

    if not results:
        return f"未找到匹配的评论（sentiment={sentiment}, keyword={keyword}）"
    return f"找到 {len(results)} 条匹配评论：\n" + "\n".join(results)


def _tool_reclassify(
    comments: list[dict[str, Any]],
    comment_indices: list[int],
    new_label: str,
) -> str:
    """执行 reclassify 工具。"""
    changed = []
    for idx in comment_indices:
        if 0 <= idx < len(comments):
            old_label = comments[idx].get("sentiment", "?")
            comments[idx]["sentiment"] = new_label
            changed.append(f"[{idx}] {old_label} -> {new_label}: {comments[idx].get('text', '')[:50]}")
        else:
            changed.append(f"[{idx}] 索引越界，跳过")
    return f"已修正 {len([c for c in changed if '->' in c])} 条评论标签：\n" + "\n".join(changed)


def _tool_get_trend(dist: dict[str, int], total: int) -> str:
    """执行 get_trend 工具。"""
    total_n = max(total, 1)
    parts = []
    for label, name in [("pos", "正向"), ("neu", "中性"), ("neg", "负向"), ("con", "争议"), ("risk", "风险")]:
        n = dist.get(label, 0)
        pct = round(n / total_n * 100, 1)
        bar = "#" * int(pct / 5)
        parts.append(f"  {name}: {n} 条 ({pct}%) {bar}")

    # 简单趋势判断
    neg_pct = dist.get("neg", 0) / total_n * 100
    risk_pct = dist.get("risk", 0) / total_n * 100
    if neg_pct + risk_pct > 30:
        trend = "负面情绪占比较高，需要重点关注"
    elif neg_pct + risk_pct > 15:
        trend = "负面情绪中等，建议关注具体负面评论内容"
    else:
        trend = "整体情绪偏正面/中性，负面风险较低"

    return "当前情绪分布：\n" + "\n".join(parts) + f"\n\n趋势判断：{trend}"


def _tool_get_cluster_detail(
    clusters: list[dict[str, Any]] | None,
    comments: list[dict[str, Any]],
    cluster_index: int,
) -> str:
    """执行 get_cluster_detail 工具。"""
    if not clusters or cluster_index < 0 or cluster_index >= len(clusters):
        return f"聚类索引 {cluster_index} 无效（共 {len(clusters) if clusters else 0} 个聚类）"

    cluster = clusters[cluster_index]
    topic = cluster.get("topic", "未知")
    size = cluster.get("size", 0)
    sentiment = cluster.get("sentiment", "neu")
    keywords = cluster.get("keywords", [])

    # 获取该聚类下的代表性评论
    rep_comments = cluster.get("representative", [])
    comment_str = ""
    if rep_comments:
        comment_str = "\n代表性评论：\n" + "\n".join(f"  - {c[:80]}{'...' if len(c) > 80 else ''}" for c in rep_comments[:5])
    else:
        comment_str = "\n（无代表性评论数据）"

    return (
        f"聚类 [{cluster_index}] 详情：\n"
        f"  话题：{topic}\n"
        f"  规模：{size} 条\n"
        f"  主导情绪：{sentiment}\n"
        f"  关键词：{'、'.join(keywords[:5]) if keywords else '无'}"
        f"{comment_str}"
    )


def _execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    comments: list[dict[str, Any]],
    dist: dict[str, int],
    clusters: list[dict[str, Any]] | None,
) -> str:
    """执行指定工具并返回结果文本。"""
    if tool_name == "search_comments":
        return _tool_search_comments(
            comments,
            arguments.get("sentiment"),
            arguments.get("keyword"),
            arguments.get("limit", 5),
        )
    elif tool_name == "reclassify":
        return _tool_reclassify(
            comments,
            arguments.get("comment_indices", []),
            arguments.get("new_label", "neu"),
        )
    elif tool_name == "get_trend":
        return _tool_get_trend(dist, len(comments))
    elif tool_name == "get_cluster_detail":
        return _tool_get_cluster_detail(
            clusters,
            comments,
            arguments.get("cluster_index", 0),
        )
    else:
        return f"未知工具：{tool_name}"


def _parse_final_response(content: str) -> dict[str, Any] | None:
    """解析 Agent 最终输出的 JSON 报告。"""
    text = content.strip()

    # 剥离思维链
    think_start = text.find("\U0001f9e0")
    if think_start < 0:
        think_start = text.find("🧠")
    if think_start >= 0:
        think_end = text.find("\U0001f4a4", think_start)
        if think_end < 0:
            think_end = text.find("💭", think_start)
        if think_end >= 0:
            text = (text[:think_start] + text[think_end + 1:]).strip()

    # 去除 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "summary" in obj:
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
            if isinstance(obj, dict) and "summary" in obj:
                return obj
        except json.JSONDecodeError:
            pass

    return None


SYSTEM_PROMPT = """你是专业的舆情分析 Agent。你的任务是基于 B 站视频评论的结构化分析数据，生成一份深度舆情分析报告。

## 工作流程
1. 先阅读初始数据摘要，形成初步判断
2. 如果发现可疑数据（如反讽被标为正向、负面评论集中但比例不高），调用工具查证
3. 查证后更新判断，决定是否需要进一步查证
4. 最终生成结构化报告

## 工具使用策略
- 如果负面评论集中指向某个具体问题，用 search_comments 搜索更多相关评论
- 如果发现评论情感标签可能有误（如反讽），用 reclassify 修正后重新评估
- 如果想了解整体情绪分布概况，用 get_trend
- 如果想深入了解某个话题聚类，用 get_cluster_detail
- 不需要查证时，直接输出最终报告

## 输出格式
当你完成分析后，输出严格 JSON（不要 markdown 代码块标记）：
{
  "summary": "整体舆情判断，2-4 句话",
  "positive": ["正面反馈要点1", "正面反馈要点2", "正面反馈要点3"],
  "negative": ["负面反馈要点1", "负面反馈要点2", "负面反馈要点3"],
  "controversy": "争议焦点分析",
  "suggestion": "建议回应策略",
  "actions": [
    {"type": "reply", "target": "评论索引或描述", "draft": "回复草稿", "reason": "回复原因"},
    {"type": "pin", "target": "评论索引或描述", "draft": "", "reason": "置顶原因"},
    {"type": "monitor_more", "target": "监控目标描述", "draft": "", "reason": "加强监控原因"},
    {"type": "alert_team", "target": "通知对象", "draft": "", "reason": "通知原因"}
  ]
}

actions 类型说明：
- reply: 建议回复某条评论（附回复草稿）
- pin: 建议置顶某条正面评论引导舆论
- monitor_more: 建议对某话题加强监控
- alert_team: 建议通知团队关注

重要：如果不需要任何 actions，返回空数组 []。"""


def run(
    video: dict[str, Any],
    comments: list[dict[str, Any]],
    dist: dict[str, int],
    keywords: list[str],
    clusters: list[dict[str, Any]] | None = None,
    max_rounds: int = MAX_ROUNDS_DEFAULT,
) -> dict[str, Any]:
    """运行 Agent，返回报告 + 推理轨迹。

    Args:
        video: 视频信息 dict
        comments: 评论列表（会被 reclassify 工具修改）
        dist: 情绪分布 {"pos": N, "neg": N, ...}
        keywords: 高频关键词列表
        clusters: 话题聚类列表
        max_rounds: 最大推理轮数

    Returns:
        {
            "summary": str,
            "positive": [str],
            "negative": [str],
            "controversy": str,
            "suggestion": str,
            "actions": [{"type": str, "target": str, "draft": str, "reason": str}],
            "ai_generated": True,
            "model": str,
            "agent_trace": [{"round": int, "thought": str, "action": str, "observation": str}],
            "agent_rounds": int,
        }
    """
    if not API_KEY:
        logger.info("Agent 模式：LLM 未配置，跳过")
        return {}

    # 构造初始消息
    context = _build_initial_context(video, comments, dist, keywords, clusters)
    user_msg = f"请分析以下舆情数据，生成报告。如需查证可调用工具。\n\n{context}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    trace: list[dict[str, str]] = []

    for round_num in range(1, max_rounds + 1):
        logger.info(f"Agent 第 {round_num}/{max_rounds} 轮推理...")
        resp = _call_llm_with_tools(messages, TOOL_DEFINITIONS)
        if not resp:
            logger.warning(f"Agent 第 {round_num} 轮 LLM 调用失败")
            break

        choice = resp["choices"][0]
        msg = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")

        # 将助手消息加入历史
        messages.append(msg)

        # 检查是否有 tool_calls
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            # 没有 tool_calls，说明 LLM 输出了最终结果
            content = msg.get("content", "")
            logger.info(f"Agent 第 {round_num} 轮输出最终结果（{len(content)} 字符）")

            # 解析最终 JSON
            result = _parse_final_response(content)
            if result:
                # 补充 actions 默认值
                result.setdefault("actions", [])
                result["ai_generated"] = True
                result["model"] = MODEL
                result["agent_trace"] = trace
                result["agent_rounds"] = round_num
                logger.info(f"Agent 报告生成成功，共 {round_num} 轮")
                return result
            else:
                logger.warning(f"Agent 最终输出 JSON 解析失败：{content[:200]}")
                break

        # 执行所有 tool_calls
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                args = {}

            logger.info(f"Agent 调用工具：{tool_name}({json.dumps(args, ensure_ascii=False)[:100]})")

            # 执行工具
            observation = _execute_tool(tool_name, args, comments, dist, clusters)

            # 记录轨迹
            trace.append({
                "round": round_num,
                "thought": msg.get("content", "")[:200] if msg.get("content") else "",
                "action": f"{tool_name}({json.dumps(args, ensure_ascii=False)[:100]})",
                "observation": observation[:300],
            })

            # 将工具结果回喂
            messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": observation,
            })

        # 如果因 tool_choice 被截断，继续下一轮
        if finish_reason == "tool_calls":
            continue

    # 超过最大轮数或解析失败
    logger.warning(f"Agent 未在 {max_rounds} 轮内完成，返回空结果")
    return {}
