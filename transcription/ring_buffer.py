import threading
import numpy as np


class RingBuffer:
    """スレッドセーフなリングバッファ"""

    def __init__(self, capacity_samples: int):
        self._buffer = np.zeros(capacity_samples, dtype=np.float32)
        self._capacity = capacity_samples
        self._write_pos = 0
        self._lock = threading.Lock()
        self._total_written = 0

    def write(self, data: np.ndarray) -> None:
        with self._lock:
            n = len(data)
            if n == 0:
                return
            if n >= self._capacity:
                self._buffer[:] = data[-self._capacity:]
                self._write_pos = 0
                self._total_written += n
                return

            end = self._write_pos + n
            if end <= self._capacity:
                self._buffer[self._write_pos:end] = data
            else:
                first = self._capacity - self._write_pos
                self._buffer[self._write_pos:] = data[:first]
                self._buffer[:n - first] = data[first:]
            self._write_pos = end % self._capacity
            self._total_written += n

    def read_latest(self, num_samples: int) -> np.ndarray:
        """最新のnum_samplesサンプルを読み取る"""
        with self._lock:
            available = min(self._total_written, self._capacity)
            n = min(num_samples, available)
            if n == 0:
                return np.zeros(0, dtype=np.float32)

            start = (self._write_pos - n) % self._capacity
            if start + n <= self._capacity:
                return self._buffer[start:start + n].copy()
            else:
                first = self._capacity - start
                return np.concatenate([
                    self._buffer[start:],
                    self._buffer[:n - first]
                ])

    @property
    def available_samples(self) -> int:
        with self._lock:
            return min(self._total_written, self._capacity)
