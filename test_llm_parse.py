"""测试 LLM JSON 解析逻辑（含 think 标签剥离、markdown 代码块、降级兜底）。

运行方式：
    python -m unittest test_llm_parse -v
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestLLMReportParse(unittest.TestCase):
    """测试 llm_report._parse_llm_json 的容错解析。"""

    @classmethod
    def setUpClass(cls):
        from analysis import llm_report
        # 用 staticmethod 包装避免被绑定为实例方法
        cls.parse = staticmethod(llm_report._parse_llm_json)

    def test_pure_json(self):
        """标准 JSON 应直接解析。"""
        raw = '{"summary":"hello","positive":["a","b"]}'
        result = self.parse(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["summary"], "hello")
        self.assertEqual(result["positive"], ["a", "b"])

    def test_closed_think_tag(self):
        """闭合 <think> 标签应正确剥离。"""
        raw = '<think>some thought process</think>{"summary":"test"}'
        result = self.parse(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["summary"], "test")

    def test_unclosed_think_tag(self):
        """未闭合 <think> 标签（DeepSeek-R1 常见）。"""
        raw = '<think>unclosed thinking...{"summary":"ok"}'
        result = self.parse(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["summary"], "ok")

    def test_think_with_fake_json(self):
        """思维链内伪 JSON + 外部真 JSON，应提取真 JSON。"""
        raw = '<think>{"score": 0.5, "fake": true}</think>{"summary":"real"}'
        result = self.parse(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["summary"], "real")

    def test_markdown_code_block(self):
        """markdown 代码块标记应被去除。"""
        raw = '```json\n{"summary":"test","positive":["x"]}\n```'
        result = self.parse(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["summary"], "test")

    def test_missing_fields_filled(self):
        """缺失字段应被填充默认值。"""
        raw = '{"summary":"only summary"}'
        result = self.parse(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["summary"], "only summary")
        # positive/negative 应有默认值
        self.assertIn(result["positive"], [["未识别到明显正向反馈"], []])
        self.assertIn(result["negative"], [["未识别到明显负面反馈"], []])

    def test_empty_content(self):
        """空内容应返回 None。"""
        self.assertIsNone(self.parse(""))

    def test_invalid_content(self):
        """完全无效内容应返回 None。"""
        self.assertIsNone(self.parse("not json at all"))


class TestLLMSentimentParse(unittest.TestCase):
    """测试 llm_sentiment._parse_labels 的标签解析。"""

    @classmethod
    def setUpClass(cls):
        from analysis import llm_sentiment
        # 用 staticmethod 包装避免被绑定为实例方法
        cls.parse = staticmethod(llm_sentiment._parse_labels)

    def test_results_wrapper(self):
        """{'results': [...]} 结构应正确解析。"""
        raw = '{"results": [{"id": 0, "label": "pos"}, {"id": 1, "label": "neg"}]}'
        labels = self.parse(raw)
        self.assertEqual(labels, {0: "pos", 1: "neg"})

    def test_array_format(self):
        """直接数组格式应正确解析。"""
        raw = '[{"id": 0, "label": "con"}, {"id": 2, "label": "risk"}]'
        labels = self.parse(raw)
        self.assertEqual(labels, {0: "con", 2: "risk"})

    def test_think_tag_stripped(self):
        """带 think 标签的响应应正确剥离。"""
        raw = '<think>分析中</think>{"results": [{"id": 0, "label": "pos"}]}'
        labels = self.parse(raw)
        self.assertEqual(labels, {0: "pos"})

    def test_markdown_stripped(self):
        """markdown 代码块应被去除。"""
        raw = '```json\n{"results": [{"id": 5, "label": "neu"}]}\n```'
        labels = self.parse(raw)
        self.assertEqual(labels, {5: "neu"})

    def test_invalid_label_filtered(self):
        """无效标签应被过滤掉。"""
        raw = '{"results": [{"id": 0, "label": "pos"}, {"id": 1, "label": "invalid"}]}'
        labels = self.parse(raw)
        self.assertEqual(labels, {0: "pos"})  # invalid 标签被过滤

    def test_empty(self):
        """空内容返回空 dict。"""
        self.assertEqual(self.parse(""), {})

    def test_invalid_content(self):
        """无效内容返回空 dict。"""
        self.assertEqual(self.parse("not json"), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
