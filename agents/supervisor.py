"""
对话控制器：面试流程状态机 + ReAct。
- 状态: INIT → QUESTION → FOLLOWUP → EVALUATE → END
- 支持: 打断、继续、结束
- 所有工具调用集中在 Supervisor（ReAct 循环）；Interviewer 只负责对话生成。
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.llm import LLMClient

try:
    from tools.base import ToolRegistry
except ImportError:
    ToolRegistry = None  # type: ignore
try:
    from agents.interviewer import Interviewer
except ImportError:
    Interviewer = None  # type: ignore


class State(str, Enum):
    """面试流程状态"""

    INIT = "init"
    QUESTION = "question"
    FOLLOWUP = "followup"
    EVALUATE = "evaluate"
    END = "end"


def _parse_react_response(text: str) -> Tuple[str, Optional[str], Optional[Dict[str, Any]]]:
    """
    解析 ReAct 一轮输出。
    返回: (kind, tool_name_or_none, tool_args_or_answer_text)
    kind in ("action", "answer")
    """
    text = (text or "").strip()
    # 先找 Answer:（可能多行）
    m = re.search(r"Answer\s*:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    if m:
        return ("answer", None, {"_text": m.group(1).strip()})

    # Action: tool_name({...}) — 从第一个 { 起匹配到配对的 }
    m = re.search(r"Action\s*:\s*(\w+)\s*\(\s*\{", text, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        start = text.index("{", m.end())
        depth = 0
        for i, c in enumerate(text[start:], start=start):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    json_str = text[start : i + 1]
                    try:
                        return ("action", name, json.loads(json_str))
                    except json.JSONDecodeError:
                        return ("action", name, {})
        return ("action", name, {})

    m = re.search(r"Action\s*:\s*(\w+)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if m:
        return ("action", m.group(1).strip(), {})

    return ("answer", None, {"_text": text[:500]})


class Supervisor:
    """
    状态机 + ReAct 控制器。
    - 状态流转: INIT → QUESTION → FOLLOWUP → EVALUATE → END
    - 支持: 打断、继续、结束
    - 工具调用全部在 run_react 中完成；需要「对候选人说话」时交给 Interviewer 生成。
    """

    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        tool_registry: Optional[Any] = None,
        interviewer: Optional[Any] = None,
    ) -> None:
        self._state = State.INIT
        self._llm = llm or LLMClient()
        self._tools = tool_registry
        self._interviewer = interviewer

    @property
    def state(self) -> State:
        return self._state

    @property
    def is_ended(self) -> bool:
        return self._state == State.END

    def continue_(self) -> Optional[State]:
        if self._state == State.END:
            return None
        next_map = {
            State.INIT: State.QUESTION,
            State.QUESTION: State.FOLLOWUP,
            State.FOLLOWUP: State.EVALUATE,
            State.EVALUATE: State.END,
        }
        self._state = next_map[self._state]
        return self._state

    def interrupt(self) -> State:
        if self._state == State.END:
            return self._state
        self._state = State.QUESTION
        return self._state

    def end(self) -> State:
        self._state = State.END
        return self._state

    def reset(self) -> State:
        self._state = State.INIT
        return self._state

    def load_resume_context(
        self,
        *,
        resume_summary: str,
        questions_summary: str,
    ) -> List[Tuple[str, str]]:
        """
        构造基于简历的上下文，供 Interviewer 生成个性化问题。
        返回对话历史 messages（role, text）列表。
        """
        messages: List[Tuple[str, str]] = [
            ("系统", "下面是候选人的简历摘要（请据此定制提问）：\n" + resume_summary),
            ("系统", "根据简历与技能匹配出的候选问题列表（供参考）：\n" + (questions_summary or "（无匹配问题）")),
        ]
        return messages

    def run_react(
        self,
        state: State,
        messages: Sequence[Tuple[str, str]],
        candidate_latest: str,
        max_steps: int = 5,
    ) -> Tuple[str, List[str]]:
        """
        执行 ReAct 循环：思考 → 选择工具或生成回复。
        - 若为工具：执行并观察，继续下一步直到达到 Answer 或步数上限。
        - 若为 Answer：将草稿交给 Interviewer 生成最终对话内容（若未配置 Interviewer 则直接用草稿）。
        返回: (对候选人要说的话, 本轮的 tool 观察列表)
        """
        observations: List[str] = []
        tools_desc = (self._tools.get_tools_description() if self._tools else "（当前无可用工具，你可以只用 Answer 决策面试节奏）")
        conv = "\n".join(f"{r}: {t}" for r, t in messages)
        reply_draft = ""

        for step in range(max_steps):
            sys_prompt = (
                "你是面试流程的控制器（Supervisor），负责：根据简历与对话上下文，自主决定：\n"
                "1) 现在应该问什么问题（或是否追问/换角度/换主题）；\n"
                "2) 什么时候继续提问，什么时候进入评估，什么时候结束整场面试。\n\n"
                "你可以使用以下工具（如果有）：\n"
                f"{tools_desc}\n\n"
                "请严格按 ReAct 风格输出，每一轮只能选择下面两种之一：\n"
                "1) 调用工具：\n"
                "   Thought: <简短思考>\n"
                "   Action: <工具名>(<JSON 参数>)\n"
                "2) 给出面试官要说的话（包含节奏意图）：\n"
                "   Thought: <简短思考>\n"
                "   Answer: <标签> 后跟一句自然语言，例如：\n"
                "     Answer: <继续提问> 你刚才提到的缓存方案中，如果出现缓存雪崩你会怎么处理？\n"
                "     Answer: <进入评估> 好的，这一题的信息已经够了，我会稍后基于你的回答给出评估。\n"
                "     Answer: <结束面试> 我已经有足够信息判断整体能力，我们先到这里，接下来我会给出综合评估。\n\n"
                "标签说明（必须出现在 Answer 开头的尖括号中）：\n"
                "- <继续提问>：表示你希望继续围绕当前/相关主题追问；\n"
                "- <进入评估>：表示本题信息已经足够，可以不再追问，进入评估阶段；\n"
                "- <结束面试>：表示整场面试信息已经足够，可以结束问答环节，进入最终综合评估。\n\n"
                "若不需要查工具，请直接给出带标签的 Answer。"
            )
            user_parts = [
                f"当前状态: {state.value}",
                f"对话历史:\n{conv}",
                f"候选人最新发言: {candidate_latest}",
            ]
            if observations:
                user_parts.append("工具观察:\n" + "\n".join(observations))
            user_prompt = "\n\n".join(user_parts)

            msgs = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ]
            try:
                out = self._llm.chat(msgs, temperature=0.3, max_tokens=400)
            except Exception as e:
                observations.append(f"LLM 调用失败: {e}")
                break
            kind, name, data = _parse_react_response(out)
            if kind == "answer":
                reply_draft = (data or {}).get("_text", "")
                break
            if kind == "action" and name and self._tools:
                obs = self._tools.run(name, **(data or {}))
                observations.append(f"[{name}] {obs}")
            else:
                observations.append("解析失败或未配置工具，结束 ReAct。")
                break

        if self._interviewer is not None and hasattr(self._interviewer, "generate_reply"):
            try:
                return (
                    self._interviewer.generate_reply(
                        state.value,
                        list(messages),
                        observations,
                        draft_reply=reply_draft or None,
                    ),
                    observations,
                )
            except Exception:
                pass
        return (reply_draft or "（暂无回复）", observations)


__all__ = ["State", "Supervisor", "_parse_react_response"]
