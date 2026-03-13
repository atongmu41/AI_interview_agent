"""
向量数据库封装（Qdrant）。

- 从 env/.env 读取 QDRANT_URL、QDRANT_API_KEY
- 提供：创建集合、写入向量、相似度搜索、按条件删除
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

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


def _get_client():
    """延迟导入 qdrant_client，便于未安装时给出明确报错。"""
    try:
        from qdrant_client import QdrantClient as _QdrantClient
        return _QdrantClient
    except ImportError as e:
        raise RuntimeError("请安装 qdrant-client：pip install qdrant-client") from e


class VectorDB:
    """
    Qdrant 向量库封装。
    - 连接：使用 QDRANT_URL、QDRANT_API_KEY（可选）
    - 集合：create_collection / 写入 / 搜索 / 删除
    """

    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        _load_dotenv_if_needed()
        self._url = url or os.getenv("QDRANT_URL") or ""
        self._api_key = api_key or os.getenv("QDRANT_API_KEY") or ""
        if not self._url:
            raise RuntimeError("未配置 Qdrant 地址，请设置环境变量 QDRANT_URL。")
        QdrantClient = _get_client()
        self._client = QdrantClient(url=self._url, api_key=self._api_key or None)

    def create_collection(
        self,
        name: str,
        vector_size: int,
        distance: str = "Cosine",
        on_disk_payload: bool = False,
    ) -> None:
        """
        创建命名集合。若已存在则跳过（不覆盖）。
        distance: Cosine | Euclid | Dot
        """
        from qdrant_client.models import Distance, VectorParams
        dist_map = {"Cosine": Distance.COSINE, "Euclid": Distance.EUCLID, "Dot": Distance.DOT}
        params = VectorParams(size=vector_size, distance=dist_map.get(distance, Distance.COSINE))
        try:
            self._client.create_collection(
                collection_name=name,
                vectors_config=params,
                on_disk_payload=on_disk_payload,
            )
        except Exception as e:
            if "already exists" in str(e).lower():
                return
            raise

    def upsert(
        self,
        collection: str,
        ids: Sequence[Union[str, int]],
        vectors: Sequence[Sequence[float]],
        payloads: Optional[Sequence[Optional[Dict[str, Any]]]] = None,
    ) -> None:
        """批量写入/更新向量与 payload。"""
        from qdrant_client.models import PointStruct
        points = []
        for i, (idx, vec) in enumerate(zip(ids, vectors)):
            payload = (payloads[i] if payloads and i < len(payloads) else None) or {}
            points.append(PointStruct(id=idx, vector=list(vec), payload=payload))
        self._client.upsert(collection_name=collection, points=points)

    def search(
        self,
        collection: str,
        vector: Sequence[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        query_filter: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        相似度搜索。返回列表，每项含 id, score, payload。
        query_filter 为 qdrant_client.models.Filter 等。
        """
        results = self._client.search(
            collection_name=collection,
            query_vector=list(vector),
            limit=limit,
            score_threshold=score_threshold,
            query_filter=query_filter,
        )
        return [
            {"id": r.id, "score": r.score, "payload": r.payload or {}}
            for r in results
        ]

    def delete(
        self,
        collection: str,
        *,
        ids: Optional[Sequence[Union[str, int]]] = None,
        filter_cond: Optional[Any] = None,
    ) -> None:
        """按 id 列表或条件删除。"""
        if ids is not None:
            self._client.delete(collection_name=collection, points_selector=ids)
        elif filter_cond is not None:
            self._client.delete(collection_name=collection, points_selector=filter_cond)
        else:
            raise ValueError("delete 需指定 ids 或 filter_cond")

    def collection_info(self, collection: str) -> Dict[str, Any]:
        """返回集合信息（向量维度、点数等）。"""
        info = self._client.get_collection(collection)
        out: Dict[str, Any] = {"points_count": info.points_count}
        try:
            p = getattr(info, "config", None) and getattr(info.config, "params", None)
            if p and hasattr(p, "vectors"):
                out["vector_size"] = getattr(p.vectors, "size", None)
        except Exception:
            pass
        return out


__all__ = ["VectorDB"]
