import logging
import threading
from typing import Optional
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)

# Whisperが無音時に生成しがちなハルシネーション（部分一致で判定）
_HALLUCINATION_SUBSTRINGS = [
    "視聴", "ご覧いただき", "チャンネル登録", "高評価",
    "お疲れ様", "おやすみなさい", "いってらっしゃい",
    "次の動画", "コメント欄",
    "Thank you for watching", "Thanks for watching",
    "Please subscribe", "See you next time",
    "Bye bye", "Goodbye", "Thank you for listening",
]


@dataclass
class TranscriptionSegment:
    text: str
    start: float
    end: float
    chunk_timestamp: float
    worker_id: int


class TranscriptionWorker:
    """faster-whisper モデル1つをラップするワーカー"""

    def __init__(self, worker_id: int, model_size: str = "small",
                 language: str = "ja", device: str = "cpu",
                 compute_type: str = "int8", beam_size: int = 3,
                 initial_prompt: Optional[str] = None):
        self._worker_id = worker_id
        self._model_size = model_size
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._initial_prompt = initial_prompt
        self._model = None
        self._lock = threading.Lock()

    def load_model(self) -> None:
        from faster_whisper import WhisperModel
        logger.info(f"Worker {self._worker_id}: モデル '{self._model_size}' を読み込み中...")
        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
            cpu_threads=4,
        )
        logger.info(f"Worker {self._worker_id}: モデル読み込み完了")

    def transcribe(self, audio: np.ndarray,
                   chunk_timestamp: float) -> list[TranscriptionSegment]:
        if self._model is None:
            raise RuntimeError("モデルが未ロード。load_model()を先に呼んでください。")

        if len(audio) < 1600:  # 0.1秒未満はスキップ
            return []

        with self._lock:
            segments, info = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=self._beam_size,
                vad_filter=True,
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=300,
                    threshold=0.3,
                ),
                initial_prompt=self._initial_prompt,
                condition_on_previous_text=False,
                without_timestamps=False,
                hallucination_silence_threshold=0.5,
                no_speech_threshold=0.4,
                repetition_penalty=1.2,
                compression_ratio_threshold=2.0,
            )

            results = []
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue

                # 1. no_speech確率が高い → 音声なしと判定
                if seg.no_speech_prob > 0.8:
                    logger.debug(f"Worker {self._worker_id}: no_speech={seg.no_speech_prob:.2f} skip: {text}")
                    continue

                # 2. avg_logprobが極端に低い → 信頼度不足
                if seg.avg_logprob < -1.5:
                    logger.debug(f"Worker {self._worker_id}: low confidence={seg.avg_logprob:.2f} skip: {text}")
                    continue

                # 3. セグメント時間に対してテキストが不自然に長い/短い
                duration = seg.end - seg.start
                if duration > 0 and len(text) / duration > 25:
                    logger.debug(f"Worker {self._worker_id}: 異常なテキスト密度 skip: {text}")
                    continue

                # 4. ハルシネーション定型文（部分一致）
                if any(p in text for p in _HALLUCINATION_SUBSTRINGS):
                    logger.debug(f"Worker {self._worker_id}: hallucination skip: {text}")
                    continue

                # 5. 同一文字/単語の繰り返し
                unique_chars = set(text)
                if len(text) >= 4 and len(unique_chars) <= 2:
                    logger.debug(f"Worker {self._worker_id}: 繰り返し skip: {text}")
                    continue

                results.append(TranscriptionSegment(
                    text=text,
                    start=seg.start,
                    end=seg.end,
                    chunk_timestamp=chunk_timestamp,
                    worker_id=self._worker_id,
                ))
            return results
