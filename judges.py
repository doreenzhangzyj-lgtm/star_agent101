"""5 位 MBTI 评委定义与异步 LLM 投票。"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from .models import CaseData, Clip, JudgeVote

JUDGES: dict[str, str] = {
    "ENTJ": (
        "你是 ENTJ（指挥官）评委。你关注转化率、目标导向、号召力（CTA）和商业传播价值。"
        "评审时优先判断：哪段内容更能驱动观众行动、更有商业传播潜力、目标是否清晰。"
    ),
    "INTJ": (
        "你是 INTJ（建筑师）评委。你关注逻辑严密性、深度思考、信息密度和结构。"
        "评审时优先判断：哪段内容论证更严谨、信息更有层次、思考更有深度。"
    ),
    "ENFJ": (
        "你是 ENFJ（主人公）评委。你关注情绪共鸣、感染力、能否建立极强的信任感。"
        "评审时优先判断：哪段内容更能打动人心、建立信任、引发情感连接。"
    ),
    "ISTP": (
        "你是 ISTP（鉴赏家）评委。你关注干货程度、实用性、语言是否简洁犀利没废话。"
        "评审时优先判断：哪段内容更有实用价值、表达是否干脆、是否少废话多信息。"
    ),
    "ENTP": (
        "你是 ENTP（辩论家）评委。你关注猎奇性、反差感、视角新颖独特、能否引发讨论。"
        "评审时优先判断：哪段内容更有话题性、视角更新颖、更容易引发讨论和传播。"
    ),
}


@dataclass
class PairwiseContext:
    clip_a: Clip
    clip_b: Clip
    full_asr: str


def _build_user_prompt(ctx: PairwiseContext) -> str:
    return f"""## 完整直播背景（ASR 上下文）
{ctx.full_asr[:8000]}

## 1v1 对决

### 切片 {ctx.clip_a.clip_id}
ASR 文本：
{ctx.clip_a.asr_text}

### 切片 {ctx.clip_b.clip_id}
ASR 文本：
{ctx.clip_b.asr_text}

请从 ENTJ/INTJ/ENFJ/ISTP/ENTP 对应视角，比较以上两个切片，选出更优秀的一个。

**必须**只输出 JSON，格式如下（不要 markdown 代码块）：
{{"winner": <切片编号>, "reason": "<100字以内的中文理由>"}}

winner 只能是 {ctx.clip_a.clip_id} 或 {ctx.clip_b.clip_id}。"""


def _parse_vote(raw: str, clip_a_id: int, clip_b_id: int) -> tuple[int, str]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"无法解析评委 JSON 输出: {raw[:300]}")
        data = json.loads(match.group(0))

    winner = int(data["winner"])
    reason = str(data.get("reason", "")).strip()
    if winner not in (clip_a_id, clip_b_id):
        raise ValueError(f"winner={winner} 不在对决切片 {clip_a_id}/{clip_b_id} 中")
    return winner, reason


class JudgePanel:
    def __init__(
        self,
        *,
        provider: str = "openai",
        model: str | None = None,
        multimodal: bool = False,
        max_concurrency: int = 10,
        dry_run: bool = False,
    ) -> None:
        self.provider = provider.lower()
        self.model = model or self._default_model()
        self.multimodal = multimodal
        self.max_concurrency = max_concurrency
        self.dry_run = dry_run
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def _default_model(self) -> str:
        if self.provider == "anthropic":
            return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        return os.getenv("OPENAI_MODEL", "gpt-4o")

    async def vote_all_pairs(
        self,
        case: CaseData,
        pairs: list[tuple[int, int]],
    ) -> list[JudgeVote]:
        clip_map = {c.clip_id: c for c in case.clips}
        tasks = []
        for clip_a_id, clip_b_id in pairs:
            ctx = PairwiseContext(
                clip_a=clip_map[clip_a_id],
                clip_b=clip_map[clip_b_id],
                full_asr=case.full_asr,
            )
            for mbti, system_prompt in JUDGES.items():
                tasks.append(self._vote_one(mbti, system_prompt, ctx))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        votes: list[JudgeVote] = []
        for result in results:
            if isinstance(result, Exception):
                raise result
            votes.append(result)
        return votes

    async def _vote_one(
        self,
        mbti: str,
        system_prompt: str,
        ctx: PairwiseContext,
    ) -> JudgeVote:
        async with self._semaphore:
            if self.dry_run:
                winner = ctx.clip_a.clip_id
                reason = f"[dry-run] {mbti} 默认选择切片 {winner}"
            else:
                raw = await self._call_llm(system_prompt, ctx)
                winner, reason = _parse_vote(raw, ctx.clip_a.clip_id, ctx.clip_b.clip_id)

            return JudgeVote(
                mbti=mbti,
                pair=(ctx.clip_a.clip_id, ctx.clip_b.clip_id),
                winner_id=winner,
                reason=reason,
            )

    async def _call_llm(self, system_prompt: str, ctx: PairwiseContext) -> str:
        user_prompt = _build_user_prompt(ctx)
        if self.multimodal:
            content = await self._build_multimodal_content(ctx, user_prompt)
        else:
            content = user_prompt

        if self.provider == "anthropic":
            return await self._call_anthropic(system_prompt, content)
        return await self._call_openai(system_prompt, content)

    async def _call_openai(self, system_prompt: str, user_content: str | list[dict[str, Any]]) -> str:
        from openai import AsyncOpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("请设置环境变量 OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        client = AsyncOpenAI(api_key=api_key, base_url=base_url) if base_url else AsyncOpenAI(api_key=api_key)

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or ""

    async def _call_anthropic(
        self,
        system_prompt: str,
        user_content: str | list[dict[str, Any]],
    ) -> str:
        from anthropic import AsyncAnthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("请设置环境变量 ANTHROPIC_API_KEY")
        client = AsyncAnthropic(api_key=api_key)

        if isinstance(user_content, str):
            blocks: list[dict[str, Any]] = [{"type": "text", "text": user_content}]
        else:
            blocks = user_content

        response = await client.messages.create(
            model=self.model,
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": blocks}],
            temperature=0.7,
        )
        parts = [block.text for block in response.content if hasattr(block, "text")]
        return "".join(parts)

    async def _build_multimodal_content(
        self,
        ctx: PairwiseContext,
        user_prompt: str,
    ) -> list[dict[str, Any]]:
        from .video_frames import extract_key_frames_base64

        blocks: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]

        for clip in (ctx.clip_a, ctx.clip_b):
            frames = await asyncio.to_thread(extract_key_frames_base64, clip.video_path, max_frames=3)
            blocks.append(
                {
                    "type": "text",
                    "text": f"\n\n--- 切片 {clip.clip_id} 关键帧（共 {len(frames)} 张）---",
                }
            )
            for index, frame_b64 in enumerate(frames, start=1):
                if self.provider == "anthropic":
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": frame_b64,
                            },
                        }
                    )
                else:
                    blocks.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{frame_b64}"},
                        }
                    )
                    blocks.append({"type": "text", "text": f"切片 {clip.clip_id} 帧 {index}"})

        return blocks
