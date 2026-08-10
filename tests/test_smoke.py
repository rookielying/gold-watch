"""穿越告警状态机 smoke test —— 无需网络，验证防骚扰/自动复位逻辑。

运行: python tests/test_smoke.py
"""
import os
import sys
import tempfile

# 确保能 import src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import AlertsConfig
from src.models import GoldQuote, iso_now
from src.alerts.engine import (
    run_alerts, load_state,
    STATE_NORMAL, STATE_ABOVE_HIGH, STATE_BELOW_LOW,
    EVT_CROSS_HIGH, EVT_CROSS_LOW, EVT_RESET,
)


def _quote(price: float) -> GoldQuote:
    return GoldQuote(
        fetched_at=iso_now(), trade_time=iso_now(),
        name="测试积存金", code="JCJ",
        last_price=price, open_price=940.0, pre_close=938.0,
        high_price=price, low_price=price, close_price=price,
        raise_amt=0.0, raise_pct=0.0, source="test",
    )


def _make_cfg(high: float = 950.0, low: float = 920.0, buffer: float = 0.005) -> AlertsConfig:
    return AlertsConfig(enabled=True, high_threshold=high, low_threshold=low, reset_buffer_pct=buffer)


def main():
    tmp = tempfile.mkdtemp()
    cfg = _make_cfg()
    passed = 0
    failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")

    print("== 穿越告警状态机测试 ==")

    # 1. NORMAL → 突破高价 → ABOVE_HIGH，发 cross_high
    rec, ev = run_alerts(cfg, _quote(955.0), tmp)
    check("1.突破高价 state=ABOVE_HIGH", rec.state == STATE_ABOVE_HIGH)
    check("1.突破高价 event=cross_high", ev is not None and ev.event_type == EVT_CROSS_HIGH)

    # 2. 已 ABOVE_HIGH，价格仍高于复位线 → 不发（防骚扰）
    rec, ev = run_alerts(cfg, _quote(956.0), tmp)
    check("2.持续高价防骚扰 state=ABOVE_HIGH", rec.state == STATE_ABOVE_HIGH)
    check("2.持续高价防骚扰 无事件", ev is None)

    # 3. 回落到复位线 (950*0.995=945.25) 以下 → 自动复位 NORMAL，发 reset
    rec, ev = run_alerts(cfg, _quote(944.0), tmp)
    check("3.回落复位 state=NORMAL", rec.state == STATE_NORMAL)
    check("3.回落复位 event=reset", ev is not None and ev.event_type == EVT_RESET)

    # 4. NORMAL → 跌破低价 → BELOW_LOW，发 cross_low
    rec, ev = run_alerts(cfg, _quote(915.0), tmp)
    check("4.跌破低价 state=BELOW_LOW", rec.state == STATE_BELOW_LOW)
    check("4.跌破低价 event=cross_low", ev is not None and ev.event_type == EVT_CROSS_LOW)

    # 5. 已 BELOW_LOW，价格仍低于复位线 → 不发（防骚扰）
    rec, ev = run_alerts(cfg, _quote(910.0), tmp)
    check("5.持续低价防骚扰 state=BELOW_LOW", rec.state == STATE_BELOW_LOW)
    check("5.持续低价防骚扰 无事件", ev is None)

    # 6. 反弹到复位线 (920*1.005=924.6) 以上 → 自动复位 NORMAL，发 reset
    rec, ev = run_alerts(cfg, _quote(926.0), tmp)
    check("6.反弹复位 state=NORMAL", rec.state == STATE_NORMAL)
    check("6.反弹复位 event=reset", ev is not None and ev.event_type == EVT_RESET)

    # 7. 区间内波动 → 不发
    rec, ev = run_alerts(cfg, _quote(935.0), tmp)
    check("7.区间内波动 state=NORMAL", rec.state == STATE_NORMAL)
    check("7.区间内波动 无事件", ev is None)

    # 8. 缓冲带内不误触发复位（仍高于 high_reset_line 945.25）
    rec, _ = run_alerts(cfg, _quote(955.0), tmp)  # 先突破
    rec, ev = run_alerts(cfg, _quote(946.0), tmp)  # 946 > 945.25 复位线，不应复位
    check("8.缓冲带内不复位 state=ABOVE_HIGH", rec.state == STATE_ABOVE_HIGH)
    check("8.缓冲带内不复位 无事件", ev is None)

    print(f"\n结果: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
