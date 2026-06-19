"""测试 B站 URL 解析、SSRF 防护、评论去重逻辑。

运行方式：
    python -m unittest test_server_utils -v

注意：B站 URL 解析涉及 HTTP 请求，仅测试纯本地逻辑（BV 号正则、SSRF host 校验、
评论去重）；不发起任何网络请求。
"""
import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBVExtraction(unittest.TestCase):
    """测试 BV 号正则提取逻辑（不发起 HTTP 请求）。"""

    def setUp(self):
        import re
        self.bv_pattern = re.compile(r"(BV[0-9A-Za-z]+)")

    def test_direct_bv_in_url(self):
        """标准 bilibili.com 链接应能提取 BV 号。"""
        url = "https://www.bilibili.com/video/BV1xx411c7mD"
        match = self.bv_pattern.search(url)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "BV1xx411c7mD")

    def test_bv_with_query_params(self):
        """带查询参数的 URL 应仍能提取 BV 号。"""
        url = "https://www.bilibili.com/video/BV1GJ411x7h7?spm_id_from=333.337.0.0"
        match = self.bv_pattern.search(url)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "BV1GJ411x7h7")

    def test_b23_short_link_no_bv(self):
        """b23.tv 短链不含 BV 号（需 HTTP 解析）。"""
        url = "https://b23.tv/abc123"
        match = self.bv_pattern.search(url)
        self.assertIsNone(match)

    def test_bare_bv_string(self):
        """纯 BV 号字符串应能被识别。"""
        match = self.bv_pattern.search("BV1xx411c7mD")
        self.assertIsNotNone(match)

    def test_non_bilibili_url(self):
        """非 B站 URL 不应匹配 BV 号。"""
        url = "https://www.youtube.com/watch?v=abc123"
        match = self.bv_pattern.search(url)
        self.assertIsNone(match)

    def test_empty_string(self):
        """空字符串不匹配。"""
        self.assertIsNone(self.bv_pattern.search(""))


class TestSSRFProtection(unittest.TestCase):
    """测试图片代理 SSRF 防护的 host 白名单校验。"""

    def setUp(self):
        # 直接 import 纯函数
        from server import _is_allowed_image_host
        self.is_allowed = staticmethod(_is_allowed_image_host)

    def test_bilibili_com_allowed(self):
        self.assertTrue(self.is_allowed("www.bilibili.com"))
        self.assertTrue(self.is_allowed("bilibili.com"))

    def test_hdslb_allowed(self):
        """B站图片 CDN 域名应放行。"""
        self.assertTrue(self.is_allowed("i0.hdslb.com"))
        self.assertTrue(self.is_allowed("i1.hdslb.com"))
        self.assertTrue(self.is_allowed("i2.hdslb.com"))

    def test_bilivideo_allowed(self):
        self.assertTrue(self.is_allowed("upos-sz-static.bilivideo.com"))

    def test_internal_ip_rejected(self):
        """内网 IP 不应在白名单。"""
        self.assertFalse(self.is_allowed("127.0.0.1"))
        self.assertFalse(self.is_allowed("10.0.0.1"))
        self.assertFalse(self.is_allowed("192.168.1.1"))
        self.assertFalse(self.is_allowed("169.254.169.254"))  # 云元数据

    def test_external_domain_rejected(self):
        """其他外部域名不应放行。"""
        self.assertFalse(self.is_allowed("evil.com"))
        self.assertFalse(self.is_allowed("attacker.bilibili.com.evil.com"))
        # 注意：bilibili.com.evil.com 不是 bilibili.com 子域，应拒绝

    def test_subdomain_spoofing_rejected(self):
        """子域欺骗攻击应被拒绝。"""
        # 不是 bilibili.com 的子域名
        self.assertFalse(self.is_allowed("bilibili.com.evil.com"))
        self.assertFalse(self.is_allowed("notbilibili.com"))

    def test_empty_host(self):
        self.assertFalse(self.is_allowed(""))


class TestDedupeComments(unittest.TestCase):
    """测试评论去重与水军过滤逻辑。"""

    def setUp(self):
        from server import dedupe_comments
        self.dedupe = dedupe_comments

    def test_dedup_by_user(self):
        """同一用户多条评论应保留最高赞一条。"""
        replies = [
            {"mid": "100", "text": "评论1", "likes": 10, "rpid": 1},
            {"mid": "100", "text": "评论2", "likes": 50, "rpid": 2},
            {"mid": "100", "text": "评论3", "likes": 30, "rpid": 3},
        ]
        result, stats = self.dedupe(replies)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "评论2")  # 最高赞
        self.assertEqual(stats["dup_by_user"], 2)

    def test_spam_filter(self):
        """归一化文本相同且>=3条，仅保留最高赞1条并打 spam_flag。"""
        spam_text = "打卡打卡打卡"
        replies = [
            {"mid": "1", "text": spam_text, "likes": 5, "rpid": 1},
            {"mid": "2", "text": spam_text, "likes": 20, "rpid": 2},
            {"mid": "3", "text": spam_text, "likes": 10, "rpid": 3},
            {"mid": "4", "text": spam_text, "likes": 8, "rpid": 4},
        ]
        result, stats = self.dedupe(replies)
        # 4 条同文本，仅保留 1 条（最高赞 likes=20）
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["likes"], 20)
        self.assertTrue(result[0].get("spam_flag"))
        self.assertEqual(stats["spam_removed"], 3)

    def test_different_users_kept(self):
        """不同用户的评论都应保留。"""
        replies = [
            {"mid": "1", "text": "用户1评论", "likes": 5, "rpid": 1},
            {"mid": "2", "text": "用户2评论", "likes": 3, "rpid": 2},
        ]
        result, _ = self.dedupe(replies)
        self.assertEqual(len(result), 2)

    def test_empty_input(self):
        """空输入应返回空列表。"""
        result, stats = self.dedupe([])
        self.assertEqual(result, [])
        self.assertEqual(stats, {"dup_by_user": 0, "spam_removed": 0})

    def test_no_spam_below_threshold(self):
        """相同文本 < 3 条不算水军。"""
        text = "相同评论"
        replies = [
            {"mid": "1", "text": text, "likes": 5, "rpid": 1},
            {"mid": "2", "text": text, "likes": 10, "rpid": 2},
        ]
        result, stats = self.dedupe(replies)
        # 2 条相同文本，不算水军，但同 mid 不同，所以都保留
        self.assertEqual(len(result), 2)
        self.assertEqual(stats["spam_removed"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
