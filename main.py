#!/usr/bin/env python3
"""
LLM Trans - リアルタイム字幕アプリ for macOS
ブラウザ等の音声をfaster-whisperで並列文字起こしし、字幕表示する。
"""

import logging
import threading
from typing import Optional
import tkinter as tk

from config import AppConfig, AudioBackendType
from audio.base import AudioBackend
from audio.sck_backend import SCKBackend
from audio.blackhole_backend import BlackHoleBackend
from transcription.pipeline import TranscriptionPipeline
from ui.app_selector import AppSelectorWindow
from ui.subtitle_overlay import SubtitleOverlay

logger = logging.getLogger(__name__)


class Application:
    """メインアプリケーションコントローラー"""

    def __init__(self):
        self._config: Optional[AppConfig] = None
        self._audio_backend: Optional[AudioBackend] = None
        self._pipeline: Optional[TranscriptionPipeline] = None
        self._selector: Optional[AppSelectorWindow] = None
        self._overlay: Optional[SubtitleOverlay] = None
        self._root: Optional[tk.Tk] = None
        self._running = False

    def run(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(threadName)s] %(levelname)s: %(message)s',
        )

        self._root = tk.Tk()

        # バックエンドの利用可否チェック
        sck_avail = SCKBackend(pid=0).is_available()
        blackhole_avail = BlackHoleBackend().is_available()

        logger.info(f"ScreenCaptureKit: {'利用可能' if sck_avail else '利用不可'}")
        logger.info(f"BlackHole: {'利用可能' if blackhole_avail else '利用不可'}")

        self._selector = AppSelectorWindow(
            root=self._root,
            on_start=self._handle_start,
            on_stop=self._handle_stop,
            sck_available=sck_avail,
            blackhole_available=blackhole_avail,
        )

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.mainloop()

    def _handle_start(self, config: AppConfig) -> None:
        self._config = config
        thread = threading.Thread(target=self._initialize_and_run, daemon=True)
        thread.start()

    def _initialize_and_run(self) -> None:
        try:
            # 1. パイプライン初期化
            self._pipeline = TranscriptionPipeline(
                config=self._config,
                on_subtitle=self._on_subtitle,
                on_status=lambda s: self._selector.set_status(s, "orange"),
            )
            self._pipeline.initialize()

            # 2. 音声バックエンド作成
            self._audio_backend = self._create_audio_backend()

            # 3. オーバーレイ作成（メインスレッドで）
            self._root.after(0, self._create_overlay)

            # 4. パイプライン開始
            self._pipeline.start()

            # 5. 音声キャプチャ開始
            self._audio_backend.start(callback=self._pipeline.feed_audio)

            self._running = True
            self._selector.set_status(
                f"字幕表示中 ({self._audio_backend.name})", "green"
            )

        except Exception as e:
            logger.error(f"起動失敗: {e}", exc_info=True)
            self._selector.set_status(f"エラー: {e}", "red")
            self._root.after(0, lambda: (
                self._selector._start_btn.config(state=tk.NORMAL),
                self._selector._stop_btn.config(state=tk.DISABLED),
            ))

    def _create_audio_backend(self) -> AudioBackend:
        if self._config.audio_backend == AudioBackendType.SCK:
            backend = SCKBackend(
                pid=self._config.target_pid,
                sample_rate=self._config.sample_rate,
            )
            if backend.is_available():
                return backend
            logger.warning("SCK利用不可、BlackHoleにフォールバック")

        backend = BlackHoleBackend(
            device_name=self._config.blackhole_device_name,
            sample_rate=self._config.sample_rate,
        )
        if backend.is_available():
            return backend

        raise RuntimeError(
            "利用可能な音声バックエンドがありません。\n"
            "画面収録の権限を許可してください。"
        )

    def _create_overlay(self) -> None:
        self._overlay = SubtitleOverlay(self._config)
        self._overlay.create(self._root)

    def _on_subtitle(self, text: str) -> None:
        if self._overlay:
            self._overlay.show_subtitle(text)

    def _handle_stop(self) -> None:
        if not self._running and self._audio_backend is None:
            return
        self._running = False

        # オーバーレイは即座に消す（メインスレッドなのでOK）
        if self._overlay:
            self._overlay.destroy()
            self._overlay = None

        # 重い停止処理はバックグラウンドで
        audio = self._audio_backend
        pipeline = self._pipeline
        self._audio_backend = None
        self._pipeline = None

        def _shutdown():
            if audio:
                audio.stop()
            if pipeline:
                pipeline.stop()
            logger.info("全コンポーネント停止完了")

        threading.Thread(target=_shutdown, daemon=True).start()

    def _on_close(self) -> None:
        self._handle_stop()
        self._root.destroy()


def main():
    app = Application()
    app.run()


if __name__ == "__main__":
    main()
