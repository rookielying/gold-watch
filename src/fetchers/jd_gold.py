"""京东金融积存金数据源。

接口：https://api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice?goldCode=CZB-JCJ
返回伦敦金/积存金实时报价（含昨收/开盘/最高/最低/涨跌）。
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any

from ..models import GoldQuote, iso_now
from .base import FetcherAdapter, FetchError, register_fetcher

_API_URL = "https://api.jdjygold.com/gw2/generic/produTools/h5/m/getGoldPrice"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://gold.jd.com/",
    "Accept": "application/json",
}


def _http_get(url: str, timeout: float = 10.0) -> str:
    """requests → urllib 降级，保证最小环境可跑。"""
    try:
        import requests  # 懒加载

        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except ImportError:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")


def _parse_trade_time(td: dict[str, Any]) -> str:
    """把 JD 返回的 tradeDateTime 结构体转成 ISO-8601 (+08:00)。"""
    y, mo, d = td["year"], td["monthValue"], td["dayOfMonth"]
    h, mi, s = td["hour"], td["minute"], td["second"]
    return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:{s:02d}+08:00"


@register_fetcher("jd_gold")
class JdGoldFetcher(FetcherAdapter):
    """京东金融积存金抓取器。"""

    def fetch(self, gold_code: str = "CZB-JCJ", **kwargs: Any) -> GoldQuote:
        url = f"{_API_URL}?goldCode={gold_code}"
        try:
            raw = _http_get(url, timeout=kwargs.get("timeout", 10.0))
        except Exception as e:
            # 网络错误可重试
            raise FetchError(f"JD 接口请求失败: {e}", retryable=True) from e

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise FetchError(f"JD 接口返回非 JSON: {e}", retryable=False) from e

        result = payload.get("resultData") or {}
        if not result.get("success"):
            raise FetchError(
                f"JD 接口返回失败: {result.get('code')} {payload.get('resultMsg')}",
                retryable=True,
            )

        d = result.get("data") or {}
        if not d or d.get("lastPrice") is None:
            # 空结果（非交易时段）—— 可重试
            raise FetchError("JD 接口返回空数据（可能非交易时段）", retryable=True)

        return GoldQuote(
            fetched_at=iso_now(),
            trade_time=_parse_trade_time(d["tradeDateTime"]),
            name=d.get("name", ""),
            code=d.get("code", ""),
            last_price=float(d["lastPrice"]),
            open_price=float(d.get("openPrice", 0) or 0),
            pre_close=float(d.get("preClose", 0) or 0),
            high_price=float(d.get("highPrice", 0) or 0),
            low_price=float(d.get("lowPrice", 0) or 0),
            close_price=float(d.get("closePrice", 0) or 0),
            raise_amt=float(d.get("raise", 0) or 0),
            raise_pct=float(d.get("raisePercent", 0) or 0),
            source="jd_gold",
        )
