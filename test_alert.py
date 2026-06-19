"""测试 Webhook 告警模块（analysis/alert.py）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPlatformDetect(unittest.TestCase):
    """测试平台自动识别。"""

    @classmethod
    def setUpClass(cls):
        from analysis import alert
        cls.detect = staticmethod(alert._detect_platform)

    def test_feishu(self):
        self.assertEqual(self.detect("https://open.feishu.cn/open-apis/bot/v2/hook/xxx"), "feishu")

    def test_larksuite(self):
        self.assertEqual(self.detect("https://open.larksuite.com/open-apis/bot/v2/hook/xxx"), "feishu")

    def test_dingtalk(self):
        self.assertEqual(self.detect("https://oapi.dingtalk.com/robot/send?access_token=xxx"), "dingtalk")

    def test_wecom(self):
        self.assertEqual(self.detect("https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"), "wecom")

    def test_generic(self):
        self.assertEqual(self.detect("https://example.com/webhook"), "generic")


class TestMessageBuild(unittest.TestCase):
    """测试消息体构造。"""

    @classmethod
    def setUpClass(cls):
        from analysis import alert
        cls.alert = alert
        cls.payload = {
            "risk": "high",
            "title": "测试视频",
            "text": "负面评论激增",
            "url": "https://www.bilibili.com/video/BV1xx",
        }

    def test_feishu_card_structure(self):
        body = self.alert._build_feishu_card(self.payload)
        self.assertEqual(body["msg_type"], "interactive")
        self.assertIn("card", body)
        self.assertEqual(body["card"]["header"]["template"], "red")
        elements = body["card"]["elements"]
        self.assertGreater(len(elements), 2)

    def test_dingtalk_markdown_structure(self):
        body = self.alert._build_dingtalk_markdown(self.payload)
        self.assertEqual(body["msgtype"], "markdown")
        self.assertIn("声浪雷达", body["markdown"]["title"])
        self.assertIn("测试视频", body["markdown"]["text"])

    def test_wecom_markdown_structure(self):
        body = self.alert._build_wecom_markdown(self.payload)
        self.assertEqual(body["msgtype"], "markdown")
        self.assertIn("测试视频", body["markdown"]["content"])

    def test_generic_json_structure(self):
        body = self.alert._build_generic_json(self.payload)
        self.assertEqual(body["source"], "shenglang-radar")
        self.assertEqual(body["risk"], "high")
        self.assertEqual(body["title"], "测试视频")
        self.assertIn("timestamp", body)

    def test_risk_emoji_mapping(self):
        """不同风险等级应映射不同 emoji 和颜色。"""
        for risk, color in [("high", "red"), ("medium", "yellow"), ("low", "green")]:
            body = self.alert._build_feishu_card({**self.payload, "risk": risk})
            self.assertEqual(body["card"]["header"]["template"], color)


class TestShouldAlert(unittest.TestCase):
    """测试告警触发判断（含冷却）。"""

    def setUp(self):
        from analysis import alert
        self.alert = alert
        # 清空冷却
        alert.reset_cooldown()
        # 保存原值
        self._orig_env = {
            "ALERT_WEBHOOK_URL": os.environ.get("ALERT_WEBHOOK_URL"),
            "ALERT_MIN_RISK": os.environ.get("ALERT_MIN_RISK"),
            "ALERT_COOLDOWN_SEC": os.environ.get("ALERT_COOLDOWN_SEC"),
        }

    def tearDown(self):
        from analysis import alert
        alert.reset_cooldown()
        for k, v in self._orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_no_webhook_url(self):
        """未配置 Webhook URL 时不应告警。"""
        os.environ.pop("ALERT_WEBHOOK_URL", None)
        self.assertFalse(self.alert.should_alert("m1", "high"))

    def test_low_risk_filtered(self):
        """风险等级低于阈值时不应告警。"""
        os.environ["ALERT_WEBHOOK_URL"] = "https://open.feishu.cn/x"
        os.environ["ALERT_MIN_RISK"] = "high"
        self.assertFalse(self.alert.should_alert("m1", "low"))
        self.assertFalse(self.alert.should_alert("m1", "medium"))
        self.assertTrue(self.alert.should_alert("m1", "high"))

    def test_medium_threshold(self):
        """阈值设为 medium 时，medium 和 high 都应告警。"""
        os.environ["ALERT_WEBHOOK_URL"] = "https://open.feishu.cn/x"
        os.environ["ALERT_MIN_RISK"] = "medium"
        self.assertFalse(self.alert.should_alert("m1", "low"))
        self.assertTrue(self.alert.should_alert("m1", "medium"))
        self.assertTrue(self.alert.should_alert("m1", "high"))

    def test_cooldown(self):
        """冷却期内不应重复告警。"""
        os.environ["ALERT_WEBHOOK_URL"] = "https://open.feishu.cn/x"
        os.environ["ALERT_MIN_RISK"] = "high"
        os.environ["ALERT_COOLDOWN_SEC"] = "60"
        self.assertTrue(self.alert.should_alert("m1", "high"))
        # 模拟已发送，记录冷却时间
        self.alert._last_alert["m1"] = __import__("time").time()
        self.assertFalse(self.alert.should_alert("m1", "high"))

    def test_different_monitors_independent(self):
        """不同任务的冷却相互独立。"""
        os.environ["ALERT_WEBHOOK_URL"] = "https://open.feishu.cn/x"
        os.environ["ALERT_MIN_RISK"] = "high"
        os.environ["ALERT_COOLDOWN_SEC"] = "3600"
        self.assertTrue(self.alert.should_alert("m1", "high"))
        self.alert._last_alert["m1"] = __import__("time").time()
        # m2 不受 m1 冷却影响
        self.assertTrue(self.alert.should_alert("m2", "high"))


class TestSendAlertNoWebhook(unittest.TestCase):
    """无 Webhook URL 时 send_alert 应安全返回 False。"""

    def setUp(self):
        self._orig = os.environ.get("ALERT_WEBHOOK_URL")
        os.environ.pop("ALERT_WEBHOOK_URL", None)

    def tearDown(self):
        if self._orig is not None:
            os.environ["ALERT_WEBHOOK_URL"] = self._orig

    def test_returns_false_when_no_url(self):
        from analysis import alert
        alert.reset_cooldown()
        result = alert.send_alert("m1", "high", "测试", "文本", "http://x")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
