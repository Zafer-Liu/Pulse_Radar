"""词典加载与分词模块 (P2 分析质量升级)

参考课程《文本分析》词典法章节，加载 Hownet / NTUSD / 清华李军三库情感词典、
知网程度级别词、停用词，并用 jieba 分词。替代 server.py 原本的子串匹配方案。

主要导出：
    POSITIVE / NEGATIVE / DEGREE / DENIAL / STOPWORDS —— 合并后的词集合/映射
    tokenize(text)        —— jieba 分词 + 去停用词
    extract_tags(text, k) —— jieba TF-IDF 关键词抽取
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Iterable

logger = logging.getLogger("lexicon")

LEXICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "lexicon")

# 知网 HowNet 程度级别词共 6 类，参考 BosonNLP / 常见中文情感分析方案赋权
# 1 极其/最 → 2.0   2 很 → 1.5   3 较 → 1.25   4 稍 → 1.0   5 欠 → 0.5   6 过 → 0.6
DEGREE_WEIGHT: dict[int, float] = {1: 2.0, 2: 1.5, 3: 1.25, 4: 1.0, 5: 0.5, 6: 0.6}

# 否定词：知网无单独文件，参考常用中文否定词表自定义。命中后翻转相邻情感词极性。
DENIAL_WORDS: frozenset[str] = frozenset({
    "不", "没", "无", "非", "未", "莫", "勿", "别", "休", "甭", "毫不", "绝不",
    "从不", "从未", "并不", "并非", "不太", "不大", "不怎么", "不能", "不是",
    "没有", "没什么", "谈不上", "算不上", "称不上", "不甚", "不怎么",
})

# 正向词库文件（Hownet 情感+评价 / NTUSD / 清华李军）
_POSITIVE_FILES = (
    ("hownet", "positive_emotion.txt"),
    ("hownet", "positive_evaluation.txt"),
    ("ntusd", "positive.txt"),
    ("tsinghua", "positive.txt"),
)
# 负向词库文件
_NEGATIVE_FILES = (
    ("hownet", "negative_emotion.txt"),
    ("hownet", "negative_evaluation.txt"),
    ("ntusd", "negative.txt"),
    ("tsinghua", "negative.txt"),
)


def _read_lines(path: str) -> list[str]:
    """自动识别 UTF-8 / GBK 编码读取文件行（三库来源编码不一）。"""
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            return raw.decode(enc).splitlines()
        except UnicodeDecodeError:
            continue
    return raw.decode("gbk", "ignore").splitlines()


def _clean_word(line: str) -> str | None:
    """从词典行提取有效词条：去引号/空白，跳过标题行、类别行、纯符号数字行。

    - 跳过含 `|` 或制表符的行（类别标记 / 标题"中文正面情感词语\\t836"）
    - 跳过 `N.` 开头的类别行
    - 跳过纯数字/英文/标点行
    - 保留含中文的有效词
    """
    w = line.strip().strip('"').strip("'").strip()
    if not w or "|" in w or "\t" in w:
        return None
    if re.match(r"^\d+\.", w):  # 类别行 "1. 极其|extreme"
        return None
    if re.match(r"^[\d\s\W]+$", w):  # 纯数字/标点
        return None
    if not re.search(r"[\u4e00-\u9fff]", w):  # 必须含中文
        return None
    # 去掉行内可能的英文注释（极少见）
    return w.split("/")[0].strip() or None


@lru_cache(maxsize=1)
def _load_positive() -> frozenset[str]:
    words: set[str] = set()
    for sub, name in _POSITIVE_FILES:
        path = os.path.join(LEXICON_DIR, sub, name)
        if not os.path.exists(path):
            logger.warning(f"正向词典缺失：{path}")
            continue
        for line in _read_lines(path):
            w = _clean_word(line)
            if w:
                words.add(w)
    logger.info(f"正向情感词典加载完成：{len(words)} 词")
    return frozenset(words)


@lru_cache(maxsize=1)
def _load_negative() -> frozenset[str]:
    words: set[str] = set()
    for sub, name in _NEGATIVE_FILES:
        path = os.path.join(LEXICON_DIR, sub, name)
        if not os.path.exists(path):
            logger.warning(f"负向词典缺失：{path}")
            continue
        for line in _read_lines(path):
            w = _clean_word(line)
            if w:
                words.add(w)
    logger.info(f"负向情感词典加载完成：{len(words)} 词")
    return frozenset(words)


@lru_cache(maxsize=1)
def _load_degree() -> dict[str, float]:
    """解析知网程度级别词：遇到 `N.` 类别行记录当前类别，后续词条归入并赋权。"""
    path = os.path.join(LEXICON_DIR, "hownet", "degree.txt")
    result: dict[str, float] = {}
    if not os.path.exists(path):
        logger.warning(f"程度级别词词典缺失：{path}")
        return result
    current_class: int | None = None
    for line in _read_lines(path):
        m = re.match(r"^(\d+)\.", line.strip())
        if m:
            current_class = int(m.group(1))
            continue
        w = _clean_word(line)
        if w and current_class is not None and current_class in DEGREE_WEIGHT:
            result[w] = DEGREE_WEIGHT[current_class]
    logger.info(f"程度级别词加载完成：{len(result)} 词")
    return result


@lru_cache(maxsize=1)
def _load_stopwords() -> frozenset[str]:
    path = os.path.join(LEXICON_DIR, "stop_words.txt")
    if not os.path.exists(path):
        logger.warning(f"停用词表缺失：{path}")
        return frozenset()
    words = {w.strip() for w in _read_lines(path) if w.strip()}
    logger.info(f"停用词表加载完成：{len(words)} 词")
    return frozenset(words)


# 对外暴露的只读集合（懒加载，首次访问时构建）
def POSITIVE() -> frozenset[str]:
    return _load_positive()


def NEGATIVE() -> frozenset[str]:
    return _load_negative()


def DEGREE() -> dict[str, float]:
    return _load_degree()


def STOPWORDS() -> frozenset[str]:
    return _load_stopwords()


# ---------- jieba 初始化 ----------

_jieba_ready = False


def _ensure_jieba() -> None:
    """加载自定义情感词典到 jieba（让分词器认识情感词，避免被切碎）。"""
    global _jieba_ready
    if _jieba_ready:
        return
    import jieba
    import jieba.analyse

    add_dict = os.path.join(LEXICON_DIR, "add_dict.txt")
    stop_words = os.path.join(LEXICON_DIR, "stop_words.txt")
    if os.path.exists(add_dict):
        jieba.load_userdict(add_dict)
    if os.path.exists(stop_words):
        jieba.analyse.set_stop_words(stop_words)
    # 调高情感词词频，避免被切散
    _jieba_ready = True
    logger.info("jieba 自定义词典与停用词已加载")


_TOKEN_TRASH = re.compile(r"^[\s\W\d]+$")


def tokenize(text: str) -> list[str]:
    """jieba 精确分词 + 去停用词 + 去纯符号数字 token。"""
    if not text:
        return []
    _ensure_jieba()
    import jieba

    stops = STOPWORDS()
    return [
        w for w in jieba.cut(text, cut_all=False)
        if w.strip() and w not in stops and not _TOKEN_TRASH.match(w)
    ]


def extract_tags(text: str, top_k: int = 20) -> list[tuple[str, float]]:
    """jieba TF-IDF 关键词抽取，返回 (词, 权重) 列表。"""
    if not text or not text.strip():
        return []
    _ensure_jieba()
    import jieba.analyse

    return [(w, float(s)) for w, s in jieba.analyse.extract_tags(text, topK=top_k, withWeight=True)]


def warmup() -> None:
    """预加载所有词典与 jieba，启动时调用以避免首次请求变慢。"""
    POSITIVE()
    NEGATIVE()
    DEGREE()
    STOPWORDS()
    _ensure_jieba()
    # 触发 jieba 分词器初始化
    tokenize("预热分词器")
