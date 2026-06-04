"""切片 ASR 自动提取（OpenAI Whisper API）。"""

from __future__ import annotations

import os
from pathlib import Path

from openai import OpenAI


def build_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("使用 --extract-asr 需要设置环境变量 OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    return OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)


def transcribe_video(video_path: Path, *, client: OpenAI | None = None) -> str:
    client = client or build_openai_client()
    model = os.getenv("WHISPER_MODEL", "whisper-1")

    with video_path.open("rb") as audio_file:
        response = client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            response_format="text",
        )

    text = response if isinstance(response, str) else str(response)
    return text.strip()
