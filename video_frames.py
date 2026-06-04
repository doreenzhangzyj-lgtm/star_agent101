"""从视频中提取关键帧，供多模态 API 使用。"""

from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Union  # 导入以兼容 Python 3.9 及以下类型注解


def extract_key_frames_base64(video_path: Path, *, max_frames: int = 3) -> list[str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("多模态模式需要安装 ffmpeg 并在 PATH 中可用")

    duration = _probe_duration(video_path, ffmpeg)
    if duration <= 0:
        timestamps = [0.0]
    else:
        step = duration / (max_frames + 1)
        timestamps = [step * (i + 1) for i in range(max_frames)]

    frames: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for index, ts in enumerate(timestamps):
            out_path = tmp_dir / f"frame_{index}.jpg"
            cmd = [
                ffmpeg,
                "-ss",
                str(ts),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-y",
                str(out_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            frames.append(base64.b64encode(out_path.read_bytes()).decode("ascii"))
    return frames


def _probe_duration(video_path: Path, ffmpeg: str) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 30.0
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 30.0
