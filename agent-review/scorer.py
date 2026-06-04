"""1v1 配对、计分与 Top 3 排名。"""

from __future__ import annotations

from itertools import combinations

from .models import CaseData, ClipScore, JudgeVote


def build_pairs(clips: list) -> list[tuple[int, int]]:
    clip_ids = [c.clip_id for c in clips]
    return list(combinations(sorted(clip_ids), 2))


def aggregate_scores(case: CaseData, votes: list[JudgeVote]) -> list[ClipScore]:
    score_map: dict[int, ClipScore] = {
        clip.clip_id: ClipScore(clip_id=clip.clip_id, total_votes=0)
        for clip in case.clips
    }

    for vote in votes:
        score = score_map[vote.winner_id]
        score.total_votes += 1
        score.supporting_votes.append(vote)

    ranked = sorted(
        score_map.values(),
        key=lambda s: (-s.total_votes, s.clip_id),
    )
    return ranked


def top_n(ranked: list[ClipScore], n: int = 3) -> list[ClipScore]:
    return ranked[: min(n, len(ranked))]
