"""
Embedding 服务封装（OpenAI 兼容接口）。

- 从 env/.env 读取 EMBEDDING_API_KEY、EMBEDDING_MODEL、EMBEDDING_BASE_URL
- 提供 embed(text) / embed_batch(texts) 将文本编码为向量
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import httpx


DEFAULT_TIMEOUT = 30.0
_DEFAULT_MODEL = "text-embedding-3-small"
_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_ENV_LOADED = False


def _load_dotenv_if_needed() -> None:
    """从项目根目录 env/.env 加载环境变量（与 llm 一致）。"""
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


class EmbeddingClient:
    """
    调用 OpenAI 兼容的 Embedding API，将文本编码为向量。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        _load_dotenv_if_needed()
        self._api_key = api_key or os.getenv("EMBEDDING_API_KEY") or ""
        self._base_url = (base_url or os.getenv("EMBEDDING_BASE_URL") or _DEFAULT_BASE_URL).rstrip("/")
        self._model = model or os.getenv("EMBEDDING_MODEL") or _DEFAULT_MODEL
        self._timeout = timeout
        if not self._api_key:
            raise RuntimeError("未配置 Embedding API Key，请设置环境变量 EMBEDDING_API_KEY。")

    def embed(self, text: str) -> List[float]:
        """
        将单条文本编码为向量。
        :param text: 输入文本
        :return: 向量列表（维度由模型决定，如 738）
        """
        vectors = self.embed_batch([text])
        return vectors[0] if vectors else []

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        将多条文本编码为向量（一次请求，减少调用次数）。
        :param texts: 输入文本列表
        :return: 向量列表的列表
        """
        if not texts:
            return []
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"input": texts, "model": self._model}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        data = resp.json()
        items = data.get("data") or []
        # 按 index 排序，保证与输入顺序一致
        items.sort(key=lambda x: x.get("index", 0))
        return [item.get("embedding", []) for item in items]


def embed(text: str) -> List[float]:
    """
    模块级便捷函数：单条文本编码为向量。
    使用默认 EmbeddingClient 配置（从环境变量读取）。
    """
    return EmbeddingClient().embed(text)


def embed_batch(texts: List[str]) -> List[List[float]]:
    """
    模块级便捷函数：多条文本编码为向量。
    """
    return EmbeddingClient().embed_batch(texts)


__all__ = ["EmbeddingClient", "embed", "embed_batch"]
