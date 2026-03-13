"""计时工具：控制面试各环节时间（占位实现）。"""
from typing import Any
from tools.base import ToolSpec

def run(action: str, duration_seconds: int = 0, **kwargs: Any) -> str:
    if action == "start":
        return "[计时] 已开始计时。"
    if action == "elapsed":
        return "[计时] 占位：返回已用时间需与具体会话绑定。"
    if action == "stop":
        return "[计时] 已停止。"
    return f"[计时] 未知 action: {action}，可用 start/elapsed/stop。"

SPEC = ToolSpec(
    name="timer",
    description="控制面试环节计时：start 开始，elapsed 查询已用时间，stop 结束",
    parameters={"type": "object", "properties": {"action": {"type": "string", "enum": ["start", "elapsed", "stop"]}, "duration_seconds": {"type": "integer"}}, "required": ["action"]},
)
