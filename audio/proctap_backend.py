import logging
import threading
from typing import Callable, Optional
import numpy as np

from audio.base import AudioBackend

logger = logging.getLogger(__name__)


class ProcTapBackend(AudioBackend):
    """ProcTap (ScreenCaptureKit) を使ったアプリ別音声キャプチャ"""

    def __init__(self, pid: int, sample_rate: int = 16000):
        self._pid = pid
        self._target_sample_rate = sample_rate
        self._capture = None
        self._capture_thread: Optional[threading.Thread] = None
        self._user_callback: Optional[Callable] = None
        self._running = False

    def is_available(self) -> bool:
        try:
            from proctap import ProcessAudioCapture
            return True
        except ImportError:
            return False

    def start(self, callback: Callable[[np.ndarray], None]) -> None:
        from proctap import ProcessAudioCapture, STANDARD_SAMPLE_RATE, STANDARD_CHANNELS

        self._user_callback = callback
        self._source_rate = STANDARD_SAMPLE_RATE  # 48000
        self._source_channels = STANDARD_CHANNELS  # 2

        def on_data(data: bytes, frames: int) -> None:
            # ProcTap outputs float32, stereo, 48kHz
            audio = np.frombuffer(data, dtype=np.float32).copy()

            # ステレオ → モノラル
            if self._source_channels == 2:
                audio = audio.reshape(-1, 2).mean(axis=1)

            # 48kHz → 16kHz (3倍ダウンサンプル)
            if self._source_rate != self._target_sample_rate:
                ratio = self._source_rate // self._target_sample_rate
                audio = audio[::ratio]

            if self._user_callback and len(audio) > 0:
                self._user_callback(audio)

        self._capture = ProcessAudioCapture(self._pid, on_data=on_data)
        self._capture.start()
        self._running = True
        logger.info(f"ProcTap: PID {self._pid} の音声キャプチャを開始 "
                    f"({self._source_rate}Hz→{self._target_sample_rate}Hz)")

    def stop(self) -> None:
        if self._capture and self._running:
            try:
                self._capture.stop()
            except Exception as e:
                logger.warning(f"ProcTap停止時エラー: {e}")
            self._running = False
            logger.info("ProcTap: 音声キャプチャを停止")

    @property
    def name(self) -> str:
        return "ProcTap (アプリ別)"
