"""
问题匹配工具：根据简历（技能/经历）匹配合适的面试问题。

优先使用规则匹配（技能标签 vs 题库标签）；
若已在向量库中构建了题目向量，则可通过向量相似度进一步排序。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from services.question_bank import QuestionBank, Question
from services.vector_db import VectorDB
from tools.base import ToolSpec


def _load_question_bank(path: str | Path) -> QuestionBank:
    root = Path(__file__).resolve().parents[1]
    qpath = root / path
    return QuestionBank.load(qpath)


def _rule_match_questions(
    qb: QuestionBank,
    *,
    role: str,
    difficulty: str,
    skills: Sequence[str],
    exclude_ids: Optional[Iterable[str]] = None,
    max_count: int = 5,
) -> List[Question]:
    """
    规则匹配：技能关键词 vs 题目 tags/expected_points。
    """
    skills_norm: Set[str] = {s.strip().lower() for s in skills if s.strip()}
    candidates = qb.sample(
        role=role,
        difficulty=difficulty,
        n=100,  # 先取一大批，再按匹配度排序
        exclude_ids=exclude_ids,
    )

    def score(q: Question) -> int:
        tags = {t.strip().lower() for t in q.tags}
        points = {p.strip().lower() for p in q.expected_points}
        return len(skills_norm & tags) * 2 + len(skills_norm & points)

    scored = sorted(
        [(q, score(q)) for q in candidates],
        key=lambda x: x[1],
        reverse=True,
    )
    return [q for q, s in scored if s > 0][:max_count]


def _vector_rank_questions(
    qb_questions: Sequence[Question],
    *,
    skills_text: str,
    collection: str = "questions",
    vector_size: int = 768,
) -> List[Question]:
    """
    向量相似度排序（可选）：假定已在 Qdrant 中建立了问题向量。
    这里只做简单的“占位式”刷新：如果 Qdrant 中无集合或无结果，则退回原顺序。

    实际部署时应在离线任务中构建好：问题 prompt/title 的向量，并写入 Qdrant，
    同时这里需要一个编码器将 skills_text 编成向量。

    当前实现仅检测集合是否存在且非空，未做实际编码/搜索。
    """
    # 占位：当前未集成向量编码器，直接返回原顺序。
    return list(qb_questions)


def run(
    skills: Sequence[str],
    *,
    role: str = "backend_python",
    difficulty: str = "junior",
    exclude_ids: Optional[Sequence[str]] = None,
    use_vector: bool = False,
    question_file: str = "config/questions.yaml",
    **kwargs: Any,
) -> str:
    """
    根据技能/经历匹配合适的问题。

    参数：
      - skills: 从简历中提取的技能关键词列表
      - role: 题库岗位 key（如 backend_python / frontend_web）
      - difficulty: 难度（如 junior / mid / senior）
      - exclude_ids: 已经问过的问题 id，避免重复
      - use_vector: 是否尝试使用向量相似度进一步排序（当前为占位实现）
      - question_file: 题库配置文件路径（相对项目根目录）

    返回 JSON 字符串：
    {
      "questions": [
        {"id": "...", "title": "...", "prompt": "...", "tags": [...], "difficulty": "..."},
        ...
      ]
    }
    """
    if not skills:
        return json.dumps({"error": "skills 为空，无法匹配问题", "questions": []}, ensure_ascii=False)

    try:
        qb = _load_question_bank(question_file)
    except Exception as e:
        return json.dumps({"error": f"加载题库失败: {e}", "questions": []}, ensure_ascii=False)

    matched = _rule_match_questions(
        qb,
        role=role,
        difficulty=difficulty,
        skills=skills,
        exclude_ids=exclude_ids,
        max_count=10,
    )

    if use_vector and matched:
        try:
            skills_text = ", ".join(skills)
            matched = _vector_rank_questions(matched, skills_text=skills_text)
        except Exception:
            # 若向量排序失败，直接忽略，使用规则结果
            pass

    data = {
        "questions": [
            {
                "id": q.id,
                "title": q.title,
                "prompt": q.prompt,
                "tags": list(q.tags),
                "difficulty": q.difficulty,
            }
            for q in matched
        ]
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


SPEC = ToolSpec(
    name="question_matcher",
    description="根据简历中的技能/经历匹配合适的题库问题（规则优先，可选向量排序）",
    parameters={
        "type": "object",
        "properties": {
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "从简历中提取的技能关键词",
            },
            "role": {"type": "string", "default": "backend_python"},
            "difficulty": {"type": "string", "default": "junior"},
            "exclude_ids": {"type": "array", "items": {"type": "string"}},
            "use_vector": {"type": "boolean", "default": False},
            "question_file": {"type": "string", "default": "config/questions.yaml"},
        },
        "required": ["skills"],
    },
)

