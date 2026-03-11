import logging
import threading
import time
from typing import Callable, Optional
import numpy as np

from config import AppConfig
from transcription.ring_buffer import RingBuffer
from transcription.worker import TranscriptionWorker
from transcription.merger import SegmentMerger
from translation import translator

logger = logging.getLogger(__name__)


class TranscriptionPipeline:
    """
    並列文字起こしパイプライン。

    2ワーカーが50%オーバーラップでチャンクを処理:
      Worker A: [0-4s][4-8s][8-12s]...
      Worker B: [2-6s][6-10s][10-14s]...
    """

    def __init__(self, config: AppConfig,
                 on_subtitle: Callable[[str], None],
                 on_status: Optional[Callable[[str], None]] = None):
        self._config = config
        self._on_subtitle = on_subtitle
        self._on_status = on_status or (lambda s: None)
        self._workers: list[TranscriptionWorker] = []
        self._merger = SegmentMerger(dedup_window_sec=10.0)
        self._ring_buffer: Optional[RingBuffer] = None
        self._running = False
        self._threads: list[threading.Thread] = []

    def initialize(self) -> None:
        """Whisperモデルをロード（時間がかかる）"""
        for i in range(self._config.num_workers):
            self._on_status(f"Loading model ({i + 1}/{self._config.num_workers})...")
            worker = TranscriptionWorker(
                worker_id=i,
                model_size=self._config.whisper_model.value,
                language=self._config.language,
                device=self._config.device,
                compute_type=self._config.compute_type,
                beam_size=self._config.beam_size,
                initial_prompt=self._config.initial_prompt,
            )
            worker.load_model()
            self._workers.append(worker)

        capacity = self._config.sample_rate * 30
        self._ring_buffer = RingBuffer(capacity)

        if self._config.enable_translation:
            self._on_status("Checking Ollama connection...")
            if not translator.check_connection(self._config.ollama_host):
                raise RuntimeError(
                    f"Cannot connect to Ollama: {self._config.ollama_host}\n"
                    "Make sure Ollama is running."
                )
            self._translation_prompt = translator.build_prompt(
                self._config.translation_source_lang,
                self._config.translation_target_lang,
            )
            logger.info(f"Ollama翻訳有効: model={self._config.ollama_model} "
                        f"{self._config.translation_source_lang}→{self._config.translation_target_lang}")

        self._on_status("Model loaded")

    def feed_audio(self, audio: np.ndarray) -> None:
        """音声バックエンドからのコールバック"""
        if self._ring_buffer:
            self._ring_buffer.write(audio)

    def start(self) -> None:
        self._running = True
        for i, worker in enumerate(self._workers):
            offset_sec = i * (self._config.chunk_duration_sec
                              * self._config.overlap_ratio)
            t = threading.Thread(
                target=self._worker_loop,
                args=(worker, offset_sec),
                daemon=True,
                name=f"whisper-worker-{i}",
            )
            t.start()
            self._threads.append(t)
        logger.info(f"パイプライン開始: {self._config.num_workers}ワーカー")

    def _worker_loop(self, worker: TranscriptionWorker,
                     initial_delay: float) -> None:
        if initial_delay > 0:
            time.sleep(initial_delay)

        chunk_samples = self._config.chunk_samples
        interval = self._config.chunk_duration_sec * self._config.overlap_ratio

        while self._running:
            loop_start = time.monotonic()

            if self._ring_buffer.available_samples < self._config.sample_rate:
                # 短いスリープを繰り返して停止フラグに素早く反応
                for _ in range(4):
                    if not self._running:
                        return
                    time.sleep(0.05)
                continue

            audio_chunk = self._ring_buffer.read_latest(chunk_samples)

            if len(audio_chunk) < self._config.sample_rate * 0.5:
                time.sleep(0.05)
                continue

            # 音量チェック: RMSが閾値未満なら無音とみなしスキップ
            rms = np.sqrt(np.mean(audio_chunk ** 2))
            if rms < 0.003:
                time.sleep(0.05)
                continue

            chunk_time = time.time()

            try:
                segments = worker.transcribe(audio_chunk, chunk_time)
                for seg in segments:
                    if seg.text:
                        deduped = self._merger.add_and_dedup(seg)
                        if deduped:
                            text = self._maybe_translate(deduped)
                            self._on_subtitle(text)
            except Exception as e:
                logger.error(f"文字起こしエラー: {e}", exc_info=True)

            elapsed = time.monotonic() - loop_start
            sleep_time = max(0.1, interval - elapsed)
            time.sleep(sleep_time)

    def _maybe_translate(self, text: str) -> str:
        """翻訳が有効なら翻訳し、失敗時は原文を返す。"""
        cfg = self._config
        if not cfg.enable_translation or not cfg.ollama_model:
            return text
        translated = translator.translate(
            text, cfg.ollama_model, self._translation_prompt, cfg.ollama_host
        )
        if translated:
            logger.debug(f"翻訳: {text} → {translated}")
            return translated
        return text

    def stop(self) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads.clear()
        logger.info("パイプライン停止")
