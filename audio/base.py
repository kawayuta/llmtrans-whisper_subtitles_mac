from abc import ABC, abstractmethod
from typing import Callable
import numpy as np


class AudioBackend(ABC):
    """音声キャプチャバックエンドの抽象基底クラス"""

    @abstractmethod
    def start(self, callback: Callable[[np.ndarray], None]) -> None:
        """音声キャプチャを開始する。callbackにfloat32 monoチャンクを渡す。"""
        ...

    @abstractmethod
    def stop(self) -> None:
        """音声キャプチャを停止する。"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """このバックエンドが利用可能かチェックする。"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
