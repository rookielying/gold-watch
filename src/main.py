"""流水线编排：抓取 → 落盘 → summary → 告警状态机 → 通知。"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Callable

from .config import Config, load_config
from .fetchers.base import FetchError, get_fetcher
from .fetchers import jd_gold  # noqa: F401  导入即注册
from .notifiers import feishu  # noqa: F401  导入即注册
from .notifiers.feishu import FeishuNotifier
from .alerts.engine import run_alerts
from .storage import Storage


def _ensure_dirs(cfg: Config) -> None:
    Path(cfg.storage.data_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.storage.state_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.storage.summary_path).parent.mkdir(parents=True, exist_ok=True)


def run(
    config_path: str | None = None,
    dry_run: bool = False,
    backoffs: tuple[int, ...] = (15, 40),
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    cfg = load_config(config_path)
    _ensure_dirs(cfg)

    # ---- 1. 抓取（指数退避重试）----
    fetcher = get_fetcher(cfg.fetcher)
    quote = None
    last_err: Exception | None = None

    if dry_run:
        # dry-run 用 Mock 数据
        from .models import GoldQuote, iso_now

        quote = GoldQuote(
            fetched_at=iso_now(),
            trade_time=iso_now(),
            name="浙商银行积存金(模拟)",
            code="JCJ",
            last_price=955.0,
            open_price=940.0,
            pre_close=938.46,
            high_price=956.0,
            low_price=935.0,
            close_price=944.55,
            raise_amt=16.54,
            raise_pct=0.0176,
            source="mock",
        )
    else:
        for i, wait in enumerate(backoffs):
            try:
                quote = fetcher.fetch(cfg.gold_code)
                break
            except FetchError as e:
                last_err = e
                if not e.retryable or i == len(backoffs) - 1:
                    print(f"[fetch] 数据源不可用: {e}", file=sys.stderr)
                    break
                print(f"[fetch] 第 {i+1} 次重试失败，{wait}s 后重试: {e}", file=sys.stderr)
                sleep_fn(wait)

    if quote is None:
        # 抓取失败 —— 发系统故障心跳
        print("[run] 抓取失败，发送故障心跳", file=sys.stderr)
        _send_failure_heartbeat(cfg, last_err)
        return {"fetched": False, "error": str(last_err)}

    # ---- 2. 落盘 ----
    storage = Storage(cfg.storage.data_dir, cfg.storage.summary_path)
    written = storage.append_quote(quote)
    print(f"[run] 抓取成功 last_price={quote.last_price} written={written}")

    # ---- 3. summary ----
    summary = storage.build_summary()

    # ---- 4. 告警状态机 ----
    rec, event = run_alerts(cfg.alerts, quote, cfg.storage.state_dir)
    print(f"[run] 状态机: state={rec.state} event={event.event_type if event else None}")

    # ---- 5. 通知 ----
    notifier = FeishuNotifier(webhook=cfg.feishu.webhook, sign_secret=cfg.feishu.sign_secret)
    if event is not None:
        notifier.send_alert(event)
        print(f"[run] 已推送告警: {event.event_type}")

    # 心跳日报（每次都发，确认系统存活）
    stats = {
        "state": rec.state,
        "historical_high": summary.get("historical_high"),
        "historical_low": summary.get("historical_low"),
        "today_count": summary.get("today_count", 0),
    }
    notifier.send_heartbeat(quote, stats)

    return {
        "fetched": True,
        "written": written,
        "price": quote.last_price,
        "state": rec.state,
        "event": event.event_type if event else None,
    }


def _send_failure_heartbeat(cfg: Config, err: Exception | None) -> None:
    """抓取失败时仍发一条心跳，告知系统异常。"""
    if not cfg.feishu.webhook:
        return
    import json
    import urllib.request

    card = {
        "header": {"title": {"tag": "plain_text", "content": "⚠️ 积存金抓取失败"}, "template": "orange"},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"数据源抓取失败：\n{err}"}},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "请检查接口可用性或非交易时段"}]},
        ],
    }
    try:
        body = json.dumps({"msg_type": "interactive", "card": card}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(cfg.feishu.webhook, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[run] 故障心跳发送失败: {e}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="积存金价格监控")
    parser.add_argument("--config", default=None, help="配置文件路径")
    parser.add_argument("--dry-run", action="store_true", help="Mock 数据，不发网络请求")
    args = parser.parse_args()

    result = run(config_path=args.config, dry_run=args.dry_run)
    print(f"[main] 完成: {result}")


if __name__ == "__main__":
    main()
