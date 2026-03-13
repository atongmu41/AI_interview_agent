from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


@dataclass(frozen=True)
class Question:
    id: str
    title: str
    prompt: str
    role: str
    difficulty: str
    tags: Sequence[str]
    expected_points: Sequence[str]


class QuestionBank:
    """
    题库系统：
    - 从 config/questions.yaml 加载
    - 按岗位(role)/难度(difficulty)分类
    - 支持动态抽题（随机、排除已问、按标签过滤、可复现 seed）
    """

    def __init__(self, questions: Sequence[Question]) -> None:
        self._questions = list(questions)
        self._index: Dict[tuple[str, str], List[Question]] = {}
        for q in self._questions:
            self._index.setdefault((q.role, q.difficulty), []).append(q)

    @staticmethod
    def load(path: str | Path) -> "QuestionBank":
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"题库文件不存在: {p}")

        try:
            import yaml  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("缺少依赖 pyyaml：请先安装 `pip install pyyaml`。") from exc

        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        roles = raw.get("roles") or {}

        questions: List[Question] = []
        for role_key, role_val in roles.items():
            difficulties = (role_val or {}).get("difficulties") or {}
            for diff_key, items in difficulties.items():
                for item in items or []:
                    questions.append(
                        Question(
                            id=str(item.get("id", "")).strip(),
                            title=str(item.get("title", "")).strip(),
                            prompt=str(item.get("prompt", "")).strip(),
                            role=str(role_key).strip(),
                            difficulty=str(diff_key).strip(),
                            tags=list(item.get("tags") or []),
                            expected_points=list(item.get("expected_points") or []),
                        )
                    )

        # 基础校验：id/prompt 不能为空，id 唯一
        ids: Set[str] = set()
        for q in questions:
            if not q.id:
                raise ValueError("题库中存在空 id 的题目。")
            if not q.prompt:
                raise ValueError(f"题目 {q.id} 的 prompt 为空。")
            if q.id in ids:
                raise ValueError(f"题库中 id 重复: {q.id}")
            ids.add(q.id)

        return QuestionBank(questions)

    def list_roles(self) -> List[str]:
        return sorted({q.role for q in self._questions})

    def list_difficulties(self, role: str) -> List[str]:
        return sorted({q.difficulty for q in self._questions if q.role == role})

    def sample(
        self,
        role: str,
        difficulty: str,
        n: int = 1,
        *,
        tags_any: Optional[Iterable[str]] = None,
        tags_all: Optional[Iterable[str]] = None,
        exclude_ids: Optional[Iterable[str]] = None,
        seed: Optional[int] = None,
    ) -> List[Question]:
        """
        动态抽题：
        - role + difficulty 定位题池
        - tags_any：命中任意标签
        - tags_all：命中全部标签
        - exclude_ids：排除已问题目
        - seed：固定随机种子（便于复现）
        """
        pool = list(self._index.get((role, difficulty), []))
        if not pool:
            return []

        exclude: Set[str] = set(exclude_ids or [])
        if exclude:
            pool = [q for q in pool if q.id not in exclude]

        if tags_any:
            any_set = {t.strip() for t in tags_any if str(t).strip()}
            if any_set:
                pool = [q for q in pool if any_set.intersection(set(q.tags))]

        if tags_all:
            all_set = {t.strip() for t in tags_all if str(t).strip()}
            if all_set:
                pool = [q for q in pool if all_set.issubset(set(q.tags))]

        if not pool or n <= 0:
            return []

        rng = random.Random(seed)
        if n >= len(pool):
            rng.shuffle(pool)
            return pool
        return rng.sample(pool, k=n)


__all__ = ["Question", "QuestionBank"]

