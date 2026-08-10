"""飞书自定义机器人通知器 —— 交互卡片推送。"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.request
from typing import Any

from ..models import GoldQuote
from .base import AlertEvent, Notifier, register_notifier


def _sign(timestamp: int, secret: str) -> str:
    """飞书 HmacSHA256 签名。"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    import base64

    return base64.b64encode(hmac_code).decode("utf-8")


def _post(webhook: str, payload: dict[str, Any]) -> bool:
    """requests → urllib 降级。NOTIFY_DRY_RUN=1 只打印不发送。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if os.environ.get("NOTIFY_DRY_RUN") == "1":
        print("[DRY_RUN] 飞书卡片 payload:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return True

    try:
        import requests

        r = requests.post(webhook, data=body, headers={"Content-Type": "application/json"}, timeout=10)
        r.raise_for_status()
        return r.json().get("StatusCode", 0) == 0 or r.json().get("code", 0) == 0
    except ImportError:
        req = urllib.request.Request(
            webhook, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8")).get("StatusCode", 0) == 0


def _fmt_change(amt: float, pct: float) -> str:
    arrow = "▲" if amt >= 0 else "▼"
    return f"{arrow} {amt:+.2f} ({pct*100:+.2f}%)"


@register_notifier("feishu")
class FeishuNotifier(Notifier):
    def __init__(self, webhook: str = "", sign_secret: str = "", **kwargs: Any):
        self.webhook = webhook
        self.sign_secret = sign_secret

    def _wrap(self, card: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"msg_type": "interactive", "card": card}
        if self.sign_secret:
            ts = int(time.time())
            payload["timestamp"] = str(ts)
            payload["sign"] = _sign(ts, self.sign_secret)
        return payload

    def send_alert(self, event: AlertEvent) -> bool:
        if not self.webhook:
            print("[feishu] 未配置 webhook，跳过告警推送")
            return False

        # 根据 event_type 选 Header 颜色
        color_map = {
            "cross_high": "red",
            "cross_low": "red",
            "reset": "green",
        }
        header_title_map = {
            "cross_high": "🔴 金价突破高价阈值",
            "cross_low": "🔴 金价跌破低价阈值",
            "reset": "🟢 金价回到区间内",
        }
        q: GoldQuote = event.quote
        card = {
            "header": {
                "title": {"tag": "plain_text", "content": header_title_map.get(event.event_type, "金价告警")},
                "template": color_map.get(event.event_type, "blue"),
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": event.message}},
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**品种**\n{q.name}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**现价**\n{event.price:.2f} 元/克"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**昨收**\n{q.pre_close:.2f}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**涨跌**\n{_fmt_change(q.raise_amt, q.raise_pct)}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**高价阈值**\n{event.threshold_high:.2f}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**低价阈值**\n{event.threshold_low:.2f}"}},
                    ],
                },
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"交易时间 {q.trade_time}  ·  状态机 {event.prev_state} → {event.state}"}]},
            ],
        }
        return _post(self.webhook, self._wrap(card))

    def send_heartbeat(self, quote: Any, stats: dict[str, Any]) -> bool:
        """心跳日报：即使无告警也发，确认系统存活。"""
        if not self.webhook:
            print("[feishu] 未配置 webhook，跳过心跳推送")
            return False

        q: GoldQuote = quote
        state = stats.get("state", "NORMAL")
        h_high = stats.get("historical_high")
        h_low = stats.get("historical_low")
        today_cnt = stats.get("today_count", 0)

        state_emoji = {"NORMAL": "⚪", "ABOVE_HIGH": "🔴", "BELOW_LOW": "🔴"}.get(state, "⚪")

        card = {
            "header": {
                "title": {"tag": "plain_text", "content": "📊 积存金价格心跳"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**品种**\n{q.name}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**现价**\n{q.last_price:.2f} 元/克"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**昨收**\n{q.pre_close:.2f}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**涨跌**\n{_fmt_change(q.raise_amt, q.raise_pct)}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**今日最高**\n{q.high_price:.2f}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**今日最低**\n{q.low_price:.2f}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**历史最高**\n{h_high:.2f}" if h_high else "**历史最高**\n-"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**历史最低**\n{h_low:.2f}" if h_low else "**历史最低**\n-"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**告警状态**\n{state_emoji} {state}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**今日采样**\n{today_cnt} 次"}},
                    ],
                },
                {"tag": "hr"},
                {"tag": "note", "elements": [{"tag": "plain_text", "content": f"交易时间 {q.trade_time}  ·  每小时自动抓取"}]},
            ],
        }
        return _post(self.webhook, self._wrap(card))
