"""知识库查询：岗位要求、评分标准等。

当前实现：
- 当 category 为 \"job_profile\" 时，使用 RAG（Embedding + Qdrant）在 job_profiles 集合中检索岗位描述片段。
- 其他类别或检索失败时，退回占位说明。
"""

from __future__ import annotations

from typing import Any, List

from services.embedding import embed
from services.vector_db import VectorDB
from tools.base import ToolSpec


def _rag_job_profile(query: str, limit: int = 5) -> str:
    """基于向量检索的岗位要求查询。"""
    if not query.strip():
        return "当前未提供有效岗位名称或查询内容。"

    db = VectorDB()
    query_vec = embed(query)
    if not query_vec:
        return "Embedding 结果为空，暂无法生成岗位要求画像。"

    hits = db.search("job_profiles", query_vec, limit=limit)
    if not hits:
        return "知识库中暂未找到与该岗位高度匹配的岗位要求。"

    parts: List[str] = []
    for h in hits:
        payload: Any = h.get("payload") or {}
        text = str(payload.get("text") or "").strip()
        if not text:
            continue
        title = str(payload.get("title") or "").strip()
        header = f"【{title}】" if title else ""
        block = f"{header}\n{text}" if header else text
        parts.append(block)

    if not parts:
        return "知识库中暂未找到与该岗位高度匹配的岗位要求。"

    return "\n\n---\n\n".join(parts)


def run(query: str, category: str = "default", **kwargs: str) -> str:
    """
    知识库查询入口。

    - 当 category == \"job_profile\"：使用 RAG 在 job_profiles 集合中检索岗位描述。
    - 其他类别或出现异常时：返回占位说明，避免影响调用方。
    """
    try:
        if category == "job_profile":
            return _rag_job_profile(query)
    except Exception as exc:
        # 出现任何异常时退回占位文案，避免中断主流程
        return f"[知识库] job_profile 检索失败: {exc}"

    return f"[知识库] 占位：query={query!r}, category={category} -> 无命中。"


SPEC = ToolSpec(
    name="knowledge_base",
    description="查询岗位要求、评分标准等知识库",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "category": {"type": "string"},
        },
        "required": ["query"],
    },
)
