"""穿越告警状态机 (Cross-Threshold Alert Engine)。

三态状态机，防骚扰 + 自动复位：
    NORMAL  ──价格>high──▶ ABOVE_HIGH   (发高价穿越告警)
    NORMAL  ──价格<low───▶ BELOW_LOW    (发低价穿越告警)
    ABOVE_HIGH ──价格回落到 high*(1-buffer) 以下──▶ NORMAL (发复位通知)
    BELOW_LOW  ──价格反弹到 low*(1+buffer) 以上──▶ NORMAL  (发复位通知)
    已处于 ABOVE_HIGH 且价格仍高于复位线 ──▶ 不发 (防骚扰)
    已处于 BELOW_LOW  且价格仍低于复位线 ──▶ 不发 (防骚扰)

状态持久化在 state/alert_state.json，保证 cron 跨次运行状态连续。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import AlertsConfig
from ..models import GoldQuote, iso_now
from ..notifiers.base import AlertEvent

# 状态机三态
STATE_NORMAL = "NORMAL"
STATE_ABOVE_HIGH = "ABOVE_HIGH"
STATE_BELOW_LOW = "BELOW_LOW"

# 事件类型
EVT_CROSS_HIGH = "cross_high"   # 突破高价
EVT_CROSS_LOW = "cross_low"     # 跌破低价
EVT_RESET = "reset"             # 回到区间内


@dataclass
class StateRecord:
    """持久化的状态机记录。"""

    state: str = STATE_NORMAL
    last_event: str = ""          # 上次触发的事件类型
    last_event_at: str = ""       # 上次触发时间
    last_event_price: float = 0.0  # 上次触发价格
    updated_at: str = ""


def _state_path(state_dir: str) -> Path:
    return Path(state_dir) / "alert_state.json"


def load_state(state_dir: str) -> StateRecord:
    p = _state_path(state_dir)
    if not p.exists():
        return StateRecord()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return StateRecord(**d)
    except Exception:
        return StateRecord()


def save_state(state_dir: str, rec: StateRecord) -> None:
    p = _state_path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(rec.__dict__, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _make_event(
    event_type: str,
    new_state: str,
    prev_state: str,
    price: float,
    cfg: AlertsConfig,
    quote: GoldQuote,
) -> AlertEvent:
    if event_type == EVT_CROSS_HIGH:
        msg = f"⚠️ 金价突破高价阈值！{quote.name} 现价 {price:.2f} > {cfg.high_threshold}"
    elif event_type == EVT_CROSS_LOW:
        msg = f"⚠️ 金价跌破低价阈值！{quote.name} 现价 {price:.2f} < {cfg.low_threshold}"
    else:  # reset
        msg = f"✅ 金价回到区间内，{quote.name} 现价 {price:.2f}"
    return AlertEvent(
        event_type=event_type,
        state=new_state,
        price=price,
        threshold_high=cfg.high_threshold,
        threshold_low=cfg.low_threshold,
        quote=quote,
        prev_state=prev_state,
        message=msg,
    )


def run_alerts(
    cfg: AlertsConfig, quote: GoldQuote, state_dir: str
) -> tuple[StateRecord, AlertEvent | None]:
    """评估状态机，返回 (新状态, 触发的事件 或 None)。

    核心防骚扰逻辑：仅在状态转换时产生事件，停留在同一状态不发。
    """
    if not cfg.enabled:
        return load_state(state_dir), None

    rec = load_state(state_dir)
    price = quote.last_price
    prev = rec.state

    # 复位线（带缓冲带，防止阈值附近震荡反复触发）
    high_reset_line = cfg.high_threshold * (1 - cfg.reset_buffer_pct)
    low_reset_line = cfg.low_threshold * (1 + cfg.reset_buffer_pct)

    new_state = prev
    event: AlertEvent | None = None

    if prev == STATE_NORMAL:
        if price > cfg.high_threshold:
            new_state = STATE_ABOVE_HIGH
            event = _make_event(EVT_CROSS_HIGH, new_state, prev, price, cfg, quote)
        elif price < cfg.low_threshold:
            new_state = STATE_BELOW_LOW
            event = _make_event(EVT_CROSS_LOW, new_state, prev, price, cfg, quote)
        # 仍在区间内 → 不发

    elif prev == STATE_ABOVE_HIGH:
        if price < high_reset_line:
            # 回落到复位线下方 → 自动复位
            new_state = STATE_NORMAL
            event = _make_event(EVT_RESET, new_state, prev, price, cfg, quote)
        # 仍高于复位线 → 不发（防骚扰）

    elif prev == STATE_BELOW_LOW:
        if price > low_reset_line:
            # 反弹到复位线上方 → 自动复位
            new_state = STATE_NORMAL
            event = _make_event(EVT_RESET, new_state, prev, price, cfg, quote)
        # 仍低于复位线 → 不发（防骚扰）

    # 持久化新状态
    if event is not None:
        rec = StateRecord(
            state=new_state,
            last_event=event.event_type,
            last_event_at=iso_now(),
            last_event_price=price,
            updated_at=iso_now(),
        )
        save_state(state_dir, rec)
    else:
        # 即使无事件也更新心跳时间
        rec.updated_at = iso_now()
        save_state(state_dir, rec)

    return rec, event
