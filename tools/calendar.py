"""日历工具：预约/查询面试时间（占位实现）。"""
from tools.base import ToolSpec

def run(action: str, slot: str = "", **kwargs: str) -> str:
    if action == "query":
        return "[日历] 占位：无可用时段。"
    if action == "book" and slot:
        return f"[日历] 占位：已预约 slot={slot}。"
    return f"[日历] 未知 action: {action}，可用 query/book。"

SPEC = ToolSpec(
    name="calendar",
    description="查询或预约面试时间：query 查空闲，book(slot) 预约",
    parameters={"type": "object", "properties": {"action": {"type": "string", "enum": ["query", "book"]}, "slot": {"type": "string"}}, "required": ["action"]},
)
