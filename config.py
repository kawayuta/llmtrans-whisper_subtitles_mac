import json
import logging
from dataclasses import dataclass, fields, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent / "settings.json"


class AudioBackendType(Enum):
    SCK = "sck"
    BLACKHOLE = "blackhole"


class WhisperModelSize(Enum):
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V3 = "large-v3"


class OverlayDisplayMode(Enum):
    SHORT = "short"
    LIST = "list"


@dataclass
class AppConfig:
    # Audio
    audio_backend: AudioBackendType = AudioBackendType.SCK
    sample_rate: int = 16000
    channels: int = 1
    chunk_duration_sec: float = 4.0
    overlap_ratio: float = 0.5

    # Transcription
    whisper_model: WhisperModelSize = WhisperModelSize.LARGE_V3
    language: str = "en"
    beam_size: int = 3
    vad_filter: bool = True
    device: str = "cpu"
    compute_type: str = "int8"
    num_workers: int = 2
    initial_prompt: Optional[str] = "日本語の字幕です。"

    # UI
    subtitle_max_lines: int = 3
    subtitle_display_seconds: float = 5.0
    font_size: int = 24
    font_family: str = "Hiragino Sans"
    overlay_opacity: float = 0.85
    overlay_bg_color: str = "#1a1a2e"
    overlay_fg_color: str = "#ffffff"
    overlay_width: int = 800
    overlay_height: int = 120
    overlay_display_mode: OverlayDisplayMode = OverlayDisplayMode.SHORT

    # Translation (Ollama)
    enable_translation: bool = False
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "translategemma:4b"
    translation_source_lang: str = "en"
    translation_target_lang: str = "ja"

    # Process selection
    target_pid: Optional[int] = None
    target_app_name: Optional[str] = None
    blackhole_device_name: str = "BlackHole 2ch"

    @property
    def chunk_samples(self) -> int:
        return int(self.sample_rate * self.chunk_duration_sec)

    @property
    def overlap_samples(self) -> int:
        return int(self.chunk_samples * self.overlap_ratio)

    def save(self, path: Path = SETTINGS_PATH) -> None:
        """UI設定項目をJSONに保存する。"""
        data = {}
        for f in fields(self):
            val = getattr(self, f.name)
            if isinstance(val, Enum):
                val = val.value
            data[f.name] = val
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            logger.warning(f"設定保存失敗: {e}")

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "AppConfig":
        """保存済みJSONから設定を復元する。ファイルがなければデフォルト。"""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            # Enumフィールドを復元
            enum_map = {
                "audio_backend": AudioBackendType,
                "whisper_model": WhisperModelSize,
                "overlay_display_mode": OverlayDisplayMode,
            }
            for key, enum_cls in enum_map.items():
                if key in data:
                    data[key] = enum_cls(data[key])
            # 未知のキーを除外
            valid_names = {f.name for f in fields(cls)}
            data = {k: v for k, v in data.items() if k in valid_names}
            return cls(**data)
        except Exception as e:
            logger.warning(f"設定読み込み失敗 (デフォルト使用): {e}")
            return cls()
