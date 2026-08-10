"""数据源适配器抽象基类 + 自注册注册表。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from ..models import GoldQuote

REGISTRY: dict[str, type["FetcherAdapter"]] = {}


class FetchError(Exception):
    """数据源异常。

    retryable=True  → 触发退避重试
    retryable=False → 立即降级 / 终止
    """

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def register_fetcher(name: str) -> Callable[[type], type]:
    """装饰器：类定义即注册到 REGISTRY。"""

    def decorator(cls: type) -> type:
        REGISTRY[name] = cls  # type: ignore[assignment]
        cls._name = name  # type: ignore[attr-defined]
        return cls

    return decorator


def get_fetcher(name: str) -> "FetcherAdapter":
    """懒加载工厂：按名称创建 fetcher 实例。"""
    if name not in REGISTRY:
        raise FetchError(f"未知数据源: {name}", retryable=False)
    return REGISTRY[name]()  # type: ignore[return-value]


class FetcherAdapter(ABC):
    """数据源适配器抽象基类。"""

    _name: str = ""

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    def fetch(self, gold_code: str, **kwargs: Any) -> GoldQuote:
        """抓取最新报价，返回 GoldQuote。失败抛 FetchError。"""
        ...
