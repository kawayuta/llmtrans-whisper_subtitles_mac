import json
import logging
import os
import struct
import subprocess
import threading
from typing import Callable, Optional
import numpy as np

from audio.base import AudioBackend

logger = logging.getLogger(__name__)

HELPER_PATH = os.path.join(os.path.dirname(__file__), "capture_helper")


class SCKBackend(AudioBackend):
    """ScreenCaptureKit Swiftヘルパーを使ったアプリ別音声キャプチャ"""

    def __init__(self, pid: int, sample_rate: int = 16000):
        self._pid = pid
        self._sample_rate = sample_rate
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._user_callback: Optional[Callable] = None
        self._running = False

    def is_available(self) -> bool:
        return os.path.isfile(HELPER_PATH) and os.access(HELPER_PATH, os.X_OK)

    def start(self, callback: Callable[[np.ndarray], None]) -> None:
        if not self.is_available():
            raise RuntimeError(f"ヘルパーが見つかりません: {HELPER_PATH}")

        self._user_callback = callback
        self._process = subprocess.Popen(
            [HELPER_PATH, str(self._pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        # stderrからREADYを待つ
        ready_thread = threading.Thread(target=self._read_stderr, daemon=True)
        ready_thread.start()

        self._running = True
        self._reader_thread = threading.Thread(
            target=self._read_audio, daemon=True, name="sck-reader"
        )
        self._reader_thread.start()
        logger.info(f"SCK: PID {self._pid} の音声キャプチャを開始")

    def _read_stderr(self) -> None:
        """stderrからログを読み取る"""
        if not self._process or not self._process.stderr:
            return
        try:
            for line in self._process.stderr:
                text = line.decode('utf-8', errors='replace').strip()
                if text:
                    logger.info(f"SCK helper: {text}")
        except Exception:
            pass

    def _read_audio(self) -> None:
        """stdoutからPCM float32データを読み取り、コールバックに渡す"""
        if not self._process or not self._process.stdout:
            return

        CHUNK_BYTES = self._sample_rate * 4 // 10  # 100ms分 (float32 = 4bytes)
        stdout = self._process.stdout

        while self._running:
            try:
                data = stdout.read(CHUNK_BYTES)
                if not data:
                    break
                # float32のアライメント確認
                remainder = len(data) % 4
                if remainder:
                    data = data[:len(data) - remainder]
                if len(data) == 0:
                    continue

                audio = np.frombuffer(data, dtype=np.float32).copy()
                if self._user_callback and len(audio) > 0:
                    self._user_callback(audio)
            except Exception as e:
                if self._running:
                    logger.error(f"SCK読み取りエラー: {e}")
                break

        logger.info("SCK: 音声読み取りスレッド終了")

    def stop(self) -> None:
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            except Exception as e:
                logger.warning(f"SCK停止時エラー: {e}")
            self._process = None
        logger.info("SCK: 音声キャプチャを停止")

    @property
    def name(self) -> str:
        return "ScreenCaptureKit (アプリ別)"


def list_apps_via_helper() -> list[dict]:
    """Swiftヘルパーを使ってアプリ一覧を取得"""
    if not os.path.isfile(HELPER_PATH):
        return []
    try:
        result = subprocess.run(
            [HELPER_PATH, "--list"],
            capture_output=True, text=True, timeout=10
        )
        apps = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    apps.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return apps
    except Exception as e:
        logger.warning(f"ヘルパーによるアプリ一覧取得失敗: {e}")
        return []
