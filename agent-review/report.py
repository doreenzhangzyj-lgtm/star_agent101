"""生成 Markdown 报告与控制台输出。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import CaseData, ClipScore


def render_markdown(
    case: CaseData,
    ranked: list[ClipScore],
    *,
    top_n: int = 3,
) -> str:
    clip_map = {c.clip_id: c for c in case.clips}
    leaders = ranked[: min(top_n, len(ranked))]
    lines = [
        "# MBTI 评委 1v1 淘汰赛 — 内容筛选报告",
        "",
        f"- **Case ID**: {case.case_id}",
        f"- **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **切片数量**: {len(case.clips)}",
        f"- **完整直播 ASR 字数**: {len(case.full_asr)}",
        "",
        "## 总票数排名",
        "",
        "| 排名 | 切片 | 总票数 |",
        "|------|------|--------|",
    ]

    for index, score in enumerate(ranked, start=1):
        lines.append(f"| {index} | 切片 {score.clip_id} | {score.total_votes} |")

    lines.extend(["", "---", "", "## Top 3 推荐内容", ""])

    for index, score in enumerate(leaders, start=1):
        clip = clip_map[score.clip_id]
        lines.extend(
            [
                f"### Top {index} — 切片 {score.clip_id}",
                "",
                f"- **总票数**: {score.total_votes}",
                f"- **视频路径**: `{clip.video_path}`",
                "",
                "#### ASR 文本",
                "",
                "```",
                clip.asr_text,
                "```",
                "",
                "#### 评委支持理由",
                "",
            ]
        )
        if not score.supporting_votes:
            lines.append("_暂无评委投票记录_")
        else:
            for vote in score.supporting_votes:
                pair_label = f"{vote.pair[0]} vs {vote.pair[1]}"
                lines.append(
                    f"- **{vote.mbti}**（{pair_label}）: {vote.reason}"
                )
        lines.append("")

    return "\n".join(lines)


def print_console_summary(case: CaseData, ranked: list[ClipScore], *, top_n: int = 3) -> None:
    clip_map = {c.clip_id: c for c in case.clips}
    leaders = ranked[: min(top_n, len(ranked))]

    print("\n" + "=" * 60)
    print("MBTI 评委 1v1 淘汰赛 — Top 3 结果")
    print("=" * 60)

    for index, score in enumerate(leaders, start=1):
        clip = clip_map[score.clip_id]
        print(f"\nTop {index} — 切片 {score.clip_id}（票数: {score.total_votes}）")
        print(f"视频: {clip.video_path}")
        print(f"ASR: {clip.asr_text[:200]}{'...' if len(clip.asr_text) > 200 else ''}")
        print("评委支持:")
        for vote in score.supporting_votes:
            print(f"  - [{vote.mbti}] {vote.reason}")


def save_report(content: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path
