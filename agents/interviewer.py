"""
面试官 Agent：仅负责对话生成，不调用任何工具。
由 Supervisor 在需要「对候选人说话」时调用，传入状态与工具结果等上下文。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.llm import LLMClient


class Interviewer:
    """
    只负责根据上下文生成面试官要说的话。
    不持有、不调用任何工具。
    """

    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self._llm = llm or LLMClient()

    def generate_reply(
        self,
        state: str,
        messages: Sequence[Tuple[str, str]],
        tool_observations: Sequence[str],
        draft_reply: Optional[str] = None,
        resume_context: Optional[str] = None,
    ) -> str:
        """
        根据当前状态、对话历史、工具观察结果（及可选的 ReAct 草稿）生成一句对候选人的回复。
        """
        conv = "\n".join(f"{role}: {text}" for role, text in messages)
        obs = "\n".join(tool_observations) if tool_observations else "（无）"
        sys_prompt = (
            "你是技术面试官，只负责生成要对候选人说的下一句话。不要调用工具，不要输出 Thought/Action。\n"
            "如果给出了简历上下文，请结合候选人的经历与技能，提出个性化、有针对性的问题或追问。"
        )
        user_prompt = (
            f"当前状态: {state}\n\n"
            f"对话历史:\n{conv}\n\n"
            f"工具观察（仅供参考）:\n{obs}\n\n"
        )
        if resume_context:
            user_prompt += f"候选人简历上下文（摘要+技能+匹配问题）：\n{resume_context}\n\n"
        if draft_reply:
            user_prompt += f"ReAct 给出的草稿（可参考或改写）: {draft_reply}\n\n"
        user_prompt += "请只输出面试官要说的一句话，不要加前缀或解释。"

        msgs: List[Dict[str, str]] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        out = self._llm.chat(msgs, temperature=0.7, max_tokens=300)
        return (out or "").strip()


__all__ = ["Interviewer"]
