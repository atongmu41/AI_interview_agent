"""
工具基类与注册表。Supervisor 通过注册表发现并调用所有工具。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolSpec:
    """工具描述，供 ReAct 提示与调用解析用。"""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema 风格，如 {"type": "object", "properties": {...}}


class ToolRegistry:
    """
    工具注册表：按 name 注册可执行函数，并生成供 LLM 使用的描述文本。
    """

    def __init__(self) -> None:
        self._specs: Dict[str, ToolSpec] = {}
        self._impls: Dict[str, Callable[..., str]] = {}

    def register(self, spec: ToolSpec, impl: Callable[..., str]) -> None:
        self._specs[spec.name] = spec
        self._impls[spec.name] = impl

    def get_spec(self, name: str) -> Optional[ToolSpec]:
        return self._specs.get(name)

    def get_tools_description(self) -> str:
        """生成供 ReAct 使用的工具列表说明（含名称、描述、参数）。"""
        lines = []
        for name, spec in self._specs.items():
            params = json.dumps(spec.parameters, ensure_ascii=False)
            lines.append(f"- {name}: {spec.description}\n  参数: {params}")
        return "\n".join(lines) if lines else "（无可用工具）"

    def run(self, name: str, **kwargs: Any) -> str:
        if name not in self._impls:
            return f"错误：未知工具 '{name}'"
        try:
            return self._impls[name](**kwargs)
        except Exception as e:
            return f"工具执行异常: {e}"

    def list_names(self) -> List[str]:
        return list(self._specs.keys())


__all__ = ["ToolSpec", "ToolRegistry"]
