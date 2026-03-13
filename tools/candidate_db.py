"""候选人数据库查询（占位实现）。"""
from tools.base import ToolSpec

def run(action: str, candidate_id: str = "", **kwargs: str) -> str:
    if action == "get" and candidate_id:
        return f"[候选人DB] 占位：未查询到 candidate_id={candidate_id}。"
    if action == "list":
        return "[候选人DB] 占位：返回空列表。"
    return f"[候选人DB] 未知 action: {action}，可用 get/list。"

SPEC = ToolSpec(
    name="candidate_db",
    description="查询候选人信息：get(candidate_id) 或 list()",
    parameters={"type": "object", "properties": {"action": {"type": "string", "enum": ["get", "list"]}, "candidate_id": {"type": "string"}}, "required": ["action"]},
)
