from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.llm import LLMClient


@dataclass(frozen=True)
class DimensionScore:
    name: str
    score: float
    rationale: str
    evidence: Sequence[str]
    confidence: float = 0.5  # 0~1，该维度打分的确定性


@dataclass(frozen=True)
class EvaluationResult:
    overall_score: float
    dimensions: Sequence[DimensionScore]
    overall_comment: str
    strengths: Sequence[str]
    improvements: Sequence[str]
    risk_flags: Sequence[str]
    overall_confidence: float = 0.5  # 0~1，整份评估的确定性

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "overall_confidence": self.overall_confidence,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "rationale": d.rationale,
                    "evidence": list(d.evidence),
                    "confidence": d.confidence,
                }
                for d in self.dimensions
            ],
            "overall_comment": self.overall_comment,
            "strengths": list(self.strengths),
            "improvements": list(self.improvements),
            "risk_flags": list(self.risk_flags),
        }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _parse_simple_prompts_yaml(yaml_text: str) -> Dict[str, Dict[str, str]]:
    """
    极简解析器：只为当前 prompts.yaml 的简单结构服务。
    """
    result: Dict[str, Dict[str, str]] = {}
    current: Optional[str] = None
    for raw in yaml_text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            current = line[:-1].strip() if line.endswith(":") else None
            if current:
                result.setdefault(current, {})
            continue
        if not current:
            continue
        stripped = line.strip()
        if ":" not in stripped:
            continue
        k, v = stripped.split(":", 1)
        result[current][k.strip()] = v.strip().strip('"').strip("'")
    return result


def _extract_json_block(text: str) -> Optional[str]:
    """
    尝试从模型输出中提取 JSON（允许前后有额外文本）。
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


class EvaluatorAgent:
    """
    评估 Agent：
    - 多维度评分：技术/沟通/逻辑
    - 生成综合评语
    """

    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        prompts_yaml_path: str | Path = "config/prompts.yaml",
    ) -> None:
        self.llm = llm or LLMClient()

        # 读取 prompts.yaml 中 evaluator 的默认参数（若不存在则使用默认值）
        try:
            p = Path(prompts_yaml_path)
            yaml_text = _read_text(p) if p.is_file() else ""
        except Exception:
            yaml_text = ""
        cfg = _parse_simple_prompts_yaml(yaml_text).get("evaluator", {})
        self.temperature = float(cfg.get("temperature", "0.3") or 0.3)
        self.max_tokens = int(cfg.get("max_tokens", "800") or 800)

    def evaluate(
        self,
        *,
        question: str,
        qa_pairs: Sequence[Tuple[str, str]],
        role: str = "",
        level: str = "",
        rubric_scale: int = 10,
    ) -> EvaluationResult:
        """
        输入：题目 + 本轮 Q/A（含追问）
        输出：技术/沟通/逻辑 三维评分 + 综合评语
        """
        transcript = "\n".join([f"Q: {q}\nA: {a}" for q, a in qa_pairs])
        system = (
            "你是技术面试评估官。请对候选人的表现做结构化评估。\n"
            "规则：\n"
            "- 评分维度固定为：技术、沟通、逻辑。\n"
            f"- 每个维度以及 overall_score 均为 0~{rubric_scale} 的数字（允许 0.5 步进）。\n"
            "- 必须证据驱动：每个维度给出 1~3 条 evidence，直接引用候选人回答原话片段。\n"
            "- 不要编造候选人未提到的信息；信息不足要说明。\n"
            "- 置信度（confidence）：0~1，表示你对该分数/评语的把握程度。证据充分、表述明确则接近 1；信息不足或需推断则降低。\n"
            "\n"
            "输出要求：只输出 JSON，不要输出额外文本。\n"
            "JSON 结构：\n"
            "{\n"
            f'  "overall_score": number,\n'
            '  "overall_confidence": number,\n'
            '  "dimensions": [\n'
            '    {"name":"技术","score":number,"rationale":"...","evidence":["..."],"confidence":number},\n'
            '    {"name":"沟通","score":number,"rationale":"...","evidence":["..."],"confidence":number},\n'
            '    {"name":"逻辑","score":number,"rationale":"...","evidence":["..."],"confidence":number}\n'
            "  ],\n"
            '  "overall_comment": "...",\n'
            '  "strengths": ["..."],\n'
            '  "improvements": ["..."],\n'
            '  "risk_flags": ["..."]\n'
            "}\n"
        )
        user = (
            f"岗位/方向：{role or '（未提供）'}\n"
            f"级别：{level or '（未提供）'}\n"
            f"题目：{question}\n\n"
            f"本轮对话记录（含追问）：\n{transcript}\n"
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        raw = self.llm.chat(messages, temperature=self.temperature, max_tokens=self.max_tokens)
        data = self._parse_result(raw)
        return self._to_result(data, rubric_scale=rubric_scale)

    def evaluate_local(
        self,
        *,
        question: str,
        qa_pairs: Sequence[Tuple[str, str]],
        rubric_scale: int = 10,
    ) -> EvaluationResult:
        """
        本地启发式评估（用于 LLM 不可用时的模块联调）。
        不追求准确，只保证输出结构稳定可用。
        """
        answer_text = "\n".join(a for _, a in qa_pairs if a).strip()
        length = len(answer_text)

        # 简单规则：长度、结构词、因果词
        has_structure = any(k in answer_text for k in ["首先", "其次", "最后", "总结", "一方面", "另一方面"])
        has_logic = any(k in answer_text for k in ["因为", "所以", "因此", "但是", "如果", "那么", "权衡", "取舍"])
        has_tech = any(
            k in answer_text.lower()
            for k in ["gil", "asyncio", "tuple", "list", "http", "sql", "cache", "锁", "线程", "进程", "协程"]
        )

        def clip(x: float) -> float:
            return max(0.0, min(float(rubric_scale), x))

        tech = clip((2.0 if has_tech else 1.0) + min(6.0, length / 80.0))
        comm = clip((2.0 if has_structure else 1.0) + min(6.0, length / 120.0))
        logic = clip((2.0 if has_logic else 1.0) + min(6.0, length / 120.0))
        overall = clip((tech + comm + logic) / 3.0)

        evidence = [answer_text[:80] + ("..." if len(answer_text) > 80 else "")] if answer_text else ["（无有效回答）"]

        default_conf = 0.5
        dims = [
            DimensionScore(name="技术", score=tech, rationale="基于回答内容长度与技术关键词的启发式估计。", evidence=evidence, confidence=default_conf),
            DimensionScore(name="沟通", score=comm, rationale="基于回答结构性表达的启发式估计。", evidence=evidence, confidence=default_conf),
            DimensionScore(name="逻辑", score=logic, rationale="基于因果/条件/权衡表达的启发式估计。", evidence=evidence, confidence=default_conf),
        ]

        strengths: List[str] = []
        improvements: List[str] = []
        risk_flags: List[str] = []

        if not answer_text:
            risk_flags.append("无回答/信息不足")
            improvements.append("建议在回答中给出定义、关键点与示例，避免空泛。")
        else:
            if has_structure:
                strengths.append("表达有一定结构。")
            else:
                improvements.append("建议用“首先/其次/最后”组织答案。")
            if has_logic:
                strengths.append("能使用因果/条件表达推理。")
            else:
                improvements.append("建议补充原因、边界条件与权衡。")
            if has_tech:
                strengths.append("能提到部分技术要点。")
            else:
                improvements.append("建议补充关键术语、机制与适用场景。")

        overall_comment = (
            f"（本地联调评估）本题“{question}”的回答整体为 {overall:.1f}/{rubric_scale}。"
            "建议结合证据进一步人工复核。"
        )

        return EvaluationResult(
            overall_score=overall,
            dimensions=dims,
            overall_comment=overall_comment,
            strengths=strengths,
            improvements=improvements,
            risk_flags=risk_flags,
            overall_confidence=0.5,
        )

    def _parse_result(self, raw: str) -> Dict[str, Any]:
        # 优先直接解析；失败则尝试抽取 JSON 块
        try:
            return json.loads(raw)
        except Exception:
            block = _extract_json_block(raw)
            if block:
                return json.loads(block)
            raise RuntimeError(f"评估输出无法解析为 JSON: {raw}")

    @staticmethod
    def _to_result(data: Dict[str, Any], *, rubric_scale: int) -> EvaluationResult:
        def _num(x: Any, default: float = 0.0) -> float:
            try:
                return float(x)
            except Exception:
                return default

        def _conf(x: Any, default: float = 0.5) -> float:
            v = _num(x, default)
            return max(0.0, min(1.0, v))

        overall_score = _num(data.get("overall_score"), 0.0)
        overall_confidence = _conf(data.get("overall_confidence"), 0.5)
        dims_in = data.get("dimensions") or []
        dims: List[DimensionScore] = []
        for d in dims_in:
            if not isinstance(d, dict):
                continue
            name = str(d.get("name", "")).strip()
            score = _num(d.get("score"), 0.0)
            rationale = str(d.get("rationale", "")).strip()
            evidence = d.get("evidence") or []
            if not isinstance(evidence, list):
                evidence = [str(evidence)]
            confidence = _conf(d.get("confidence"), 0.5)
            dims.append(
                DimensionScore(
                    name=name,
                    score=max(0.0, min(float(rubric_scale), score)),
                    rationale=rationale,
                    evidence=[str(x) for x in evidence if str(x).strip()],
                    confidence=confidence,
                )
            )

        overall_comment = str(data.get("overall_comment", "")).strip()
        strengths = data.get("strengths") or []
        improvements = data.get("improvements") or []
        risk_flags = data.get("risk_flags") or []

        def _list(v: Any) -> List[str]:
            if isinstance(v, list):
                return [str(x).strip() for x in v if str(x).strip()]
            if v is None:
                return []
            s = str(v).strip()
            return [s] if s else []

        return EvaluationResult(
            overall_score=max(0.0, min(float(rubric_scale), overall_score)),
            dimensions=dims,
            overall_comment=overall_comment,
            strengths=_list(strengths),
            improvements=_list(improvements),
            risk_flags=_list(risk_flags),
            overall_confidence=overall_confidence,
        )


__all__ = ["EvaluatorAgent", "EvaluationResult", "DimensionScore"]

