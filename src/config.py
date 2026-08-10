"""配置加载 —— JSON-Wins 策略 + 环境变量安全注入。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AlertsConfig:
    enabled: bool = True
    high_threshold: float = 950.0
    low_threshold: float = 920.0
    reset_buffer_pct: float = 0.005  # 复位缓冲带，防止阈值附近震荡


@dataclass
class FeishuConfig:
    enabled: bool = True
    webhook: str = ""        # 运行时从环境变量注入
    sign_secret: str = ""    # 运行时从环境变量注入


@dataclass
class StorageConfig:
    data_dir: str = "data/gold"
    state_dir: str = "state"
    summary_path: str = "docs/data/summary.json"


@dataclass
class Config:
    timezone: str = "Asia/Shanghai"
    fetcher: str = "jd_gold"
    gold_code: str = "CZB-JCJ"
    storage: StorageConfig = field(default_factory=StorageConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    feishu: FeishuConfig = field(default_factory=FeishuConfig)

    # 原始字典，供 notifier 等模块按需读取未知字段
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def _load_raw(config_path: str | None) -> dict[str, Any]:
    """JSON-Wins：优先读 config.json，降级 config.yaml。"""
    p = Path(config_path) if config_path else Path("config.json")
    # 1. JSON 优先
    json_path = p if p.suffix == ".json" else p.with_suffix(".json")
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    # 2. YAML 降级
    yaml_path = p if p.suffix in (".yaml", ".yml") else p.with_suffix(".yaml")
    if yaml_path.exists():
        try:
            import yaml  # 懒加载
            return yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except ImportError:
            pass
    # 3. 兜底
    return {}


def load_config(config_path: str | None = None) -> Config:
    raw = _load_raw(config_path)

    # 环境变量安全注入（覆盖明文凭证）
    feishu_raw = raw.get("notifiers", {}).get("feishu", {})
    webhook = os.environ.get(feishu_raw.get("secret_env", "FEISHU_WEBHOOK"), "")
    sign_secret = os.environ.get(feishu_raw.get("sign_secret_env", "FEISHU_SECRET"), "")

    cfg = Config(
        timezone=raw.get("timezone", "Asia/Shanghai"),
        fetcher=raw.get("fetcher", "jd_gold"),
        gold_code=raw.get("gold_code", "CZB-JCJ"),
        storage=StorageConfig(**raw.get("storage", {})),
        alerts=AlertsConfig(**raw.get("alerts", {})),
        feishu=FeishuConfig(
            enabled=feishu_raw.get("enabled", True),
            webhook=webhook,
            sign_secret=sign_secret,
        ),
        raw=raw,
    )
    return cfg
