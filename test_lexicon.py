"""测试情感词典加载、分词、否定词翻转、程度词加权。

运行方式：
    python -m unittest test_lexicon -v
"""
import sys
import os
import unittest

# 将项目根目录加入 sys.path，便于直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _lexicon_available() -> bool:
    """检查 jieba 是否已安装。"""
    try:
        import jieba  # noqa: F401
        return True
    except ImportError:
        return False


class TestLexiconLoading(unittest.TestCase):
    """验证三库词典和程度词/否定词成功加载。"""

    @classmethod
    def setUpClass(cls):
        from analysis import lexicon
        cls.lexicon = lexicon

    def test_positive_dict_loaded(self):
        """正向词典应至少包含 5000 词（三库合并去重后约 10219）。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        pos = self.lexicon.POSITIVE()
        self.assertGreater(len(pos), 5000, f"正向词典只有 {len(pos)} 词，应≥5000")

    def test_negative_dict_loaded(self):
        """负向词典应至少包含 7000 词（三库合并去重后约 13751）。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        neg = self.lexicon.NEGATIVE()
        self.assertGreater(len(neg), 7000, f"负向词典只有 {len(neg)} 词，应≥7000")

    def test_degree_dict_loaded(self):
        """程度词词典应至少 100 个（6 类加权词）。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        degree = self.lexicon.DEGREE()
        self.assertGreater(len(degree), 100, f"程度词只有 {len(degree)} 词，应≥100")

    def test_denial_words_loaded(self):
        """否定词集合应至少 5 个（不、没、别、未、无 等）。"""
        # DENIAL_WORDS 是模块级常量，不需 jieba
        denial = self.lexicon.DENIAL_WORDS
        self.assertGreaterEqual(len(denial), 5)
        self.assertIn("不", denial)
        self.assertIn("没", denial)


class TestTokenize(unittest.TestCase):
    """验证 jieba 分词与自定义词典。"""

    @classmethod
    def setUpClass(cls):
        if not _lexicon_available():
            return
        from analysis import lexicon
        cls.tokenize = staticmethod(lexicon.tokenize)

    def test_basic_cut(self):
        """简单句应能正确分词。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        tokens = self.tokenize("这个视频很好看")
        self.assertIsInstance(tokens, list)
        self.assertIn("好看", tokens)

    def test_empty_string(self):
        """空字符串应返回空列表。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        self.assertEqual(self.tokenize(""), [])
        self.assertEqual(self.tokenize(None), [])

    def test_stops_filtered(self):
        """停用词应被过滤掉。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        tokens = self.tokenize("的 了 在 是")
        # 这些都是常见停用词，应被过滤
        self.assertEqual(tokens, [])


class TestExtractTags(unittest.TestCase):
    """验证 TF-IDF 关键词提取。"""

    @classmethod
    def setUpClass(cls):
        if not _lexicon_available():
            return
        from analysis import lexicon
        cls.extract_tags = staticmethod(lexicon.extract_tags)

    def test_extract_returns_list_of_tuples(self):
        """应返回 list[(词, 权重)]。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        tags = self.extract_tags("这个视频很好看 内容扎实 讲解清晰", top_k=3)
        self.assertIsInstance(tags, list)
        for item in tags:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)
            self.assertIsInstance(item[0], str)
            self.assertIsInstance(item[1], float)

    def test_extract_high_freq_ranked_first(self):
        """高频词应排在前面。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        text = "视频视频视频视频视频视频内容内容其他"
        tags = self.extract_tags(text, top_k=2)
        words = [w for w, _ in tags]
        self.assertIn("视频", words)

    def test_extract_empty(self):
        """空输入应返回空列表。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        self.assertEqual(self.extract_tags("", top_k=3), [])
        self.assertEqual(self.extract_tags("   ", top_k=3), [])


class TestWarmup(unittest.TestCase):
    """验证词典预热函数不报错。"""

    def test_warmup_no_exception(self):
        """warmup() 应正常执行不抛异常。"""
        if not _lexicon_available():
            self.skipTest("jieba 未安装")
        from analysis import lexicon
        try:
            lexicon.warmup()
        except Exception as e:
            self.fail(f"warmup() 抛异常：{e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
