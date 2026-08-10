"""JSONL 存储层 —— Git-as-DB，按月分片，幂等去重。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import GoldQuote, iso_now, month_of, today_shanghai


class Storage:
    """积存金报价落盘 + summary 编译。"""

    def __init__(self, data_dir: str, summary_path: str):
        self.data_dir = Path(data_dir)
        self.summary_path = Path(summary_path)

    # ---------- 落盘 ----------
    def append_quote(self, quote: GoldQuote) -> bool:
        """幂等去重写入。按抓取月份分片。返回是否为新写入。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        shard = self.data_dir / f"{month_of(quote.fetched_at)}.jsonl"
        key = quote.dedup_key

        existing: set[str] = set()
        if shard.exists():
            for line in shard.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    existing.add(GoldQuote.from_dict(json.loads(line)).dedup_key)
                except Exception:
                    continue

        if key in existing:
            return False  # 重复，跳过

        with shard.open("a", encoding="utf-8") as f:
            f.write(quote.to_json() + "\n")
        return True

    # ---------- 查询 ----------
    def _read_all(self) -> list[GoldQuote]:
        quotes: list[GoldQuote] = []
        if not self.data_dir.exists():
            return quotes
        for shard in sorted(self.data_dir.glob("*.jsonl")):
            for line in shard.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    quotes.append(GoldQuote.from_dict(json.loads(line)))
                except Exception:
                    continue
        return quotes

    def latest(self) -> GoldQuote | None:
        qs = self._read_all()
        if not qs:
            return None
        return max(qs, key=lambda q: q.fetched_at)

    def historical_high(self) -> float | None:
        qs = self._read_all()
        if not qs:
            return None
        return max(q.last_price for q in qs)

    def historical_low(self) -> float | None:
        qs = self._read_all()
        if not qs:
            return None
        return min(q.last_price for q in qs)

    def today_series(self) -> list[GoldQuote]:
        today = today_shanghai()
        return [q for q in self._read_all() if q.trade_time[:10] == today]

    # ---------- summary ----------
    def build_summary(self) -> dict[str, Any]:
        """编译 docs/data/summary.json 供前端看板使用。"""
        qs = self._read_all()
        today = today_shanghai()
        today_qs = [q for q in qs if q.trade_time[:10] == today]
        today_qs.sort(key=lambda q: q.fetched_at)

        latest_q = qs[-1] if qs else None  # type: ignore[arg-type]
        series = [
            {"t": q.trade_time, "p": q.last_price, "source": q.source}
            for q in today_qs
        ]

        summary = {
            "generated_at": iso_now(),
            "gold_code": latest_q.code if latest_q else "",
            "name": latest_q.name if latest_q else "",
            "latest": {
                "price": latest_q.last_price if latest_q else None,
                "trade_time": latest_q.trade_time if latest_q else None,
                "open": latest_q.open_price if latest_q else None,
                "pre_close": latest_q.pre_close if latest_q else None,
                "high": latest_q.high_price if latest_q else None,
                "low": latest_q.low_price if latest_q else None,
                "raise_amt": latest_q.raise_amt if latest_q else None,
                "raise_pct": latest_q.raise_pct if latest_q else None,
            },
            "historical_high": max(q.last_price for q in qs) if qs else None,
            "historical_low": min(q.last_price for q in qs) if qs else None,
            "today_series": series,
            "today_count": len(today_qs),
            "total_count": len(qs),
        }

        self.summary_path.parent.mkdir(parents=True, exist_ok=True)
        self.summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return summary
