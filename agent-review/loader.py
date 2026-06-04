"""从 Case demo 目录自动读取完整 ASR、切片视频与切片 ASR。"""

from __future__ import annotations

import re
from pathlib import Path

from .models import CaseData, Clip


FULL_ASR_CANDIDATES = (
    "完整直播 ASR.txt",
    "完整直播ASR.txt",
    "full_asr.txt",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_case_demo_dir() -> Path:
    return _project_root() / "Case demo"


def list_case_dirs(case_demo_dir: Path | None = None) -> list[Path]:
    root = case_demo_dir or default_case_demo_dir()
    if not root.is_dir():
        raise FileNotFoundError(f"Case demo 目录不存在: {root}")
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))


def _find_full_asr(case_dir: Path) -> Path:
    for name in FULL_ASR_CANDIDATES:
        candidate = case_dir / name
        if candidate.is_file():
            return candidate

    matches = sorted(
        p
        for p in case_dir.glob("*ASR*.txt")
        if "Cut" not in p.name and "切片" not in p.name
    )
    if len(matches) == 1:
        return matches[0]
    if matches:
        return matches[0]

    raise FileNotFoundError(
        f"未在 {case_dir} 找到完整直播 ASR（尝试过: {', '.join(FULL_ASR_CANDIDATES)} 及 *ASR*.txt）"
    )


def _extract_clip_number(path: Path) -> int | None:
    match = re.search(r"(?:Cut|clip)[_\s-]?(\d+)", path.stem, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)", path.stem)
    return int(match.group(1)) if match else None


def _find_clip_videos(case_dir: Path) -> list[Path]:
    videos = sorted(
        p
        for p in case_dir.iterdir()
        if p.suffix.lower() == ".mp4" and p.is_file()
    )
    if not videos:
        raise FileNotFoundError(f"未在 {case_dir} 找到任何 .mp4 切片视频")

    numbered = [(p, _extract_clip_number(p)) for p in videos]
    if all(n is not None for _, n in numbered):
        numbered.sort(key=lambda item: item[1])  # type: ignore[arg-type]
        return [p for p, _ in numbered]
    return videos


def _cut_asr_candidates(case_dir: Path, clip_num: int, prefix: str) -> list[Path]:
    names = [
        f"切片 {clip_num} ASR.txt",
        f"切片{clip_num} ASR.txt",
        f"切片{clip_num}ASR.txt",
        f"{prefix}_Cut{clip_num}_ASR.txt",
        f"{prefix}_Cut{clip_num} ASR.txt",
        f"Cut{clip_num}_ASR.txt",
        f"clip_{clip_num}.txt",
        f"clip_{clip_num}_asr.txt",
    ]
    return [case_dir / name for name in names if (case_dir / name).is_file()]


def _find_cut_asr(case_dir: Path, clip_num: int, prefix: str) -> Path | None:
    candidates = _cut_asr_candidates(case_dir, clip_num, prefix)
    return candidates[0] if candidates else None


def load_case(
    case_dir: Path,
    *,
    extract_asr: bool = False,
    whisper_client=None,
) -> CaseData:
    """加载单个 case 目录下的完整 ASR 与 3-4 个切片。"""
    case_dir = case_dir.resolve()
    if not case_dir.is_dir():
        raise FileNotFoundError(f"Case 目录不存在: {case_dir}")

    case_id = case_dir.name
    prefix = case_id
    full_asr_path = _find_full_asr(case_dir)
    full_asr = full_asr_path.read_text(encoding="utf-8").strip()
    video_paths = _find_clip_videos(case_dir)

    if not (3 <= len(video_paths) <= 4):
        raise ValueError(
            f"Case {case_id} 需要 3-4 个切片，当前找到 {len(video_paths)} 个: "
            + ", ".join(p.name for p in video_paths)
        )

    clips: list[Clip] = []
    for index, video_path in enumerate(video_paths, start=1):
        clip_num = _extract_clip_number(video_path) or index
        asr_path = _find_cut_asr(case_dir, clip_num, prefix)
        if asr_path:
            asr_text = asr_path.read_text(encoding="utf-8").strip()
        elif extract_asr:
            from .asr_extract import transcribe_video

            asr_text = transcribe_video(video_path, client=whisper_client)
        else:
            asr_text = (
                f"[切片 {clip_num} 暂无独立 ASR 文件；"
                f"请补充切片 ASR 或使用 --extract-asr 自动转写]"
            )

        clips.append(
            Clip(
                clip_id=clip_num,
                video_path=video_path.resolve(),
                asr_text=asr_text,
            )
        )

    clips.sort(key=lambda c: c.clip_id)
    return CaseData(case_id=case_id, case_dir=case_dir, full_asr=full_asr, clips=clips)


def load_case_by_id(
    case_id: str,
    case_demo_dir: Path | None = None,
    **kwargs,
) -> CaseData:
    case_dir = (case_demo_dir or default_case_demo_dir()) / case_id
    return load_case(case_dir, **kwargs)
