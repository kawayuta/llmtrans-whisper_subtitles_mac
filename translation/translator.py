import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)

LANGUAGES = {
    "en": "English",
    "ja": "Japanese",
    "zh-Hans": "Chinese (Simplified)",
    "zh-Hant": "Chinese (Traditional)",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "it": "Italian",
    "vi": "Vietnamese",
    "th": "Thai",
}


def build_prompt(source_code: str, target_code: str) -> str:
    """translategemma形式のプロンプトを生成する。"""
    src = LANGUAGES.get(source_code, source_code)
    tgt = LANGUAGES.get(target_code, target_code)
    return (
        f"You are a professional {src} ({source_code}) to {tgt} ({target_code}) "
        f"translator. Your goal is to accurately convey the meaning and nuances of the "
        f"original {src} text while adhering to {tgt} grammar, vocabulary, "
        f"and cultural sensitivities.\n\n"
        f"Produce only the {tgt} translation, without any additional "
        f"explanations or commentary. Please translate the following {src} "
        f"text into {tgt}:"
    )


def list_models(host: str = "http://localhost:11434") -> list[str]:
    """Ollamaから利用可能なモデル一覧を取得する。"""
    try:
        resp = httpx.get(f"{host}/api/tags", timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.warning(f"Ollamaモデル一覧取得失敗: {e}")
        return []


def translate(
    text: str,
    model: str,
    system_prompt: str,
    host: str = "http://localhost:11434",
) -> Optional[str]:
    """Ollamaでテキストを翻訳する。失敗時はNoneを返す。

    system_promptは翻訳指示、textは翻訳対象テキスト。
    translategemmaの形式に合わせ、指示 + 空行2つ + テキストを
    単一のuserメッセージとして /api/chat に送る。
    """
    if not text or not model or not system_prompt:
        return None

    content = f"{system_prompt}\n\n\n{text}"

    try:
        resp = httpx.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": content}],
                "stream": False,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json().get("message", {}).get("content", "").strip()
        return result if result else None
    except Exception as e:
        logger.error(f"翻訳エラー: {e}")
        return None


def check_connection(host: str = "http://localhost:11434") -> bool:
    """Ollamaへの接続テスト。"""
    try:
        resp = httpx.get(f"{host}/api/tags", timeout=_TIMEOUT)
        resp.raise_for_status()
        return True
    except Exception:
        return False
