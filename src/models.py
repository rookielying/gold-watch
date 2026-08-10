"""数据模型 + 时区工具。"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any

_SHANGHAI = timezone(timedelta(hours=8))


def now_shanghai() -> datetime:
    return datetime.now(_SHANGHAI)


def iso_now() -> str:
    return now_shanghai().isoformat()


def today_shanghai() -> str:
    return now_shanghai().strftime("%Y-%m-%d")


def month_of(dt_str: str) -> str:
    """'2026-08-10T16:20:02+08:00' → '2026-08'"""
    return dt_str[:7]


@dataclass
class GoldQuote:
    """积存金报价快照 —— 系统核心数据载体。"""

    fetched_at: str          # 抓取时间 ISO-8601 (+08:00)
    trade_time: str          # 交易所时间 ISO-8601 (+08:00)
    name: str                # 品种名（浙商银行积存金）
    code: str                # 品种代码（JCJ）
    last_price: float        # 最新价 (元/克)
    open_price: float        # 开盘价
    pre_close: float         # 昨收价
    high_price: float        # 最高价
    low_price: float         # 最低价
    close_price: float       # 收盘价
    raise_amt: float         # 涨跌额
    raise_pct: float         # 涨跌幅 (小数, 0.0065 = 0.65%)
    source: str = "jd_gold"  # 数据源

    @property
    def dedup_key(self) -> str:
        """去重主键：按交易分钟去重（同一分钟内多次抓取只保留一条）。"""
        return f"{self.trade_time[:16]}|{self.source}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GoldQuote":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})
