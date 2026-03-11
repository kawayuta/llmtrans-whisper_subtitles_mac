import threading
from collections import deque
from typing import Optional

from transcription.worker import TranscriptionSegment


class SegmentMerger:
    """並列ワーカーからの文字起こし結果を重複排除・マージする"""

    def __init__(self, dedup_window_sec: float = 10.0):
        self._window_sec = dedup_window_sec
        self._recent: deque[TranscriptionSegment] = deque()
        self._lock = threading.Lock()

    def add_and_dedup(self, segment: TranscriptionSegment) -> Optional[str]:
        """セグメントを追加し、重複でなければテキストを返す。重複ならNone。"""
        with self._lock:
            cutoff = segment.chunk_timestamp - self._window_sec
            while self._recent and self._recent[0].chunk_timestamp < cutoff:
                self._recent.popleft()

            for existing in self._recent:
                if self._is_duplicate(existing.text, segment.text):
                    if len(segment.text) > len(existing.text):
                        existing.text = segment.text
                    return None

            self._recent.append(segment)
            return segment.text

    @staticmethod
    def _is_duplicate(text_a: str, text_b: str) -> bool:
        if not text_a or not text_b:
            return False

        if len(text_a) <= len(text_b):
            shorter, longer = text_a, text_b
        else:
            shorter, longer = text_b, text_a

        # 完全に含まれていれば重複
        if shorter in longer:
            return True

        # 最長共通部分文字列で判定
        match_len = 0
        len_s = len(shorter)
        for i in range(len_s):
            for j in range(len_s, i, -1):
                substr = shorter[i:j]
                if len(substr) <= match_len:
                    break
                if substr in longer:
                    match_len = len(substr)
                    break

        return match_len / len(shorter) > 0.6 if shorter else False
