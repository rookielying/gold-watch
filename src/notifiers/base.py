"""通知器抽象基类 + 自注册注册表。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

REGISTRY: dict[str, type["Notifier"]] = {}


def register_notifier(name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        REGISTRY[name] = cls  # type: ignore[assignment]
        cls._name = name  # type: ignore[attr-defined]
        return cls

    return decorator


def get_notifier(name: str, **kwargs: Any) -> "Notifier":
    if name not in REGISTRY:
        raise ValueError(f"未知通知器: {name}")
    return REGISTRY[name](**kwargs)  # type: ignore[return-value]


@dataclass
class AlertEvent:
    """告警事件 —— 通知器的标准入参。"""

    event_type: str        # "cross_high" | "cross_low" | "reset" | "heartbeat"
    state: str             # "ABOVE_HIGH" | "BELOW_LOW" | "NORMAL"
    price: float           # 触发价格
    threshold_high: float
    threshold_low: float
    quote: Any             # GoldQuote
    prev_state: str        # 状态机前一状态
    message: str = ""      # 人类可读消息


class Notifier(ABC):
    """通知器抽象基类。"""

    _name: str = ""

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def send_alert(self, event: AlertEvent) -> bool:
        """发送穿越告警 / 复位通知，返回是否成功。"""
        ...

    @abstractmethod
    def send_heartbeat(self, quote: Any, stats: dict[str, Any]) -> bool:
        """发送心跳日报（即使无告警也发，确认系统存活）。"""
        ...
