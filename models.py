from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Clip:
    clip_id: int
    video_path: Path
    asr_text: str


@dataclass
class CaseData:
    case_id: str
    case_dir: Path
    full_asr: str
    clips: list[Clip]


@dataclass
class JudgeVote:
    mbti: str
    pair: tuple[int, int]
    winner_id: int
    reason: str


@dataclass
class ClipScore:
    clip_id: int
    total_votes: int
    supporting_votes: list[JudgeVote] = field(default_factory=list)
