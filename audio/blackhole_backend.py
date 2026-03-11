import logging
from typing import Callable, Optional
import numpy as np
import sounddevice as sd

from audio.base import AudioBackend

logger = logging.getLogger(__name__)


class BlackHoleBackend(AudioBackend):
    """BlackHole + sounddevice を使ったシステム音声キャプチャ"""

    def __init__(self, device_name: str = "BlackHole 2ch",
                 sample_rate: int = 16000):
        self._device_name = device_name
        self._sample_rate = sample_rate
        self._stream: Optional[sd.InputStream] = None
        self._user_callback: Optional[Callable] = None

    def is_available(self) -> bool:
        try:
            devices = sd.query_devices()
            return any(
                self._device_name in d['name']
                for d in devices
                if d['max_input_channels'] > 0
            )
        except Exception:
            return False

    def _find_device_index(self) -> int:
        devices = sd.query_devices()
        for i, d in enumerate(devices):
            if self._device_name in d['name'] and d['max_input_channels'] > 0:
                return i
        raise RuntimeError(f"BlackHole デバイス '{self._device_name}' が見つかりません")

    def start(self, callback: Callable[[np.ndarray], None]) -> None:
        device_idx = self._find_device_index()
        self._user_callback = callback

        def sd_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"sounddevice: {status}")
            mono = indata[:, 0] if indata.ndim > 1 else indata.flatten()
            if self._user_callback:
                self._user_callback(mono.copy())

        self._stream = sd.InputStream(
            device=device_idx,
            channels=1,
            samplerate=self._sample_rate,
            dtype='float32',
            blocksize=int(self._sample_rate * 0.1),
            callback=sd_callback,
        )
        self._stream.start()
        logger.info(f"BlackHole: デバイス '{self._device_name}' で音声キャプチャを開始")

    def stop(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning(f"BlackHole停止時エラー: {e}")
            self._stream = None
            logger.info("BlackHole: 音声キャプチャを停止")

    @property
    def name(self) -> str:
        return "BlackHole (システム音声)"
