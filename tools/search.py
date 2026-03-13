"""搜索工具：查公司/岗位信息（通过 SerpAPI）。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import httpx

from tools.base import ToolSpec

_ENV_LOADED = False


def _load_dotenv_if_needed() -> None:
    """从项目根目录 env/.env 加载 SERPAPI_API_KEY。"""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    current_file = Path(__file__).resolve()
    project_root = current_file.parents[1]
    env_path = project_root / "env" / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    _ENV_LOADED = True


def _serpapi_search(query: str, engine: str = "google", **kwargs: Any) -> str:
    _load_dotenv_if_needed()
    api_key = os.getenv("SERPAPI_API_KEY") or ""
    if not api_key:
        return "[搜索] 未配置 SERPAPI_API_KEY，无法调用 SerpAPI。"

    params: Dict[str, Any] = {
        "api_key": api_key,
        "engine": engine,
        "q": query,
        "hl": "zh-cn",
    }
    # 允许透传一些常见参数（location、num 等）
    for k in ("location", "num", "gl"):
        if k in kwargs and kwargs[k] is not None:
            params[k] = kwargs[k]

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get("https://serpapi.com/search", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return f"[搜索] SerpAPI 调用失败: {e}"

    # 提取前几条结果做简要摘要，避免返回整个 JSON
    snippets = []
    for item in (data.get("organic_results") or [])[:3]:
        title = item.get("title") or ""
        snippet = item.get("snippet") or item.get("content") or ""
        link = item.get("link") or ""
        if not title and not snippet:
            continue
        parts = [p for p in [title, snippet, link] if p]
        snippets.append(" | ".join(parts))

    if not snippets:
        return "[搜索] SerpAPI 无结果或结果为空。"

    return "[搜索结果]\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(snippets))


def run(query: str, source: str = "web", **kwargs: Any) -> str:
    """
    使用 SerpAPI 搜索公司/岗位信息。
    - query: 查询内容
    - source: 预留字段，目前仅支持 'web'
    其余 kwargs 会透传给 SerpAPI（如 location、num 等）。
    """
    if not query.strip():
        return "[搜索] query 为空。"
    return _serpapi_search(query=query, **kwargs)


SPEC = ToolSpec(
    name="search",
    description="搜索公司或岗位相关信息（通过 SerpAPI）",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "source": {"type": "string", "default": "web"},
            "location": {"type": "string"},
            "num": {"type": "integer"},
        },
        "required": ["query"],
    },
)
