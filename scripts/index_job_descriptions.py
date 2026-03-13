from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

from services.embedding import embed, embed_batch
from services.vector_db import VectorDB


def _load_md_chunks(md_path: Path) -> List[str]:
    if not md_path.is_file():
        raise FileNotFoundError(f"岗位描述文件不存在: {md_path}")

    text = md_path.read_text(encoding="utf-8")
    # 按 "\n### " 分块，首段通常为目录/前言
    parts = re.split(r"\n### ", text)
    chunks: List[str] = []
    for i, part in enumerate(parts):
        if i == 0:
            # 丢弃不含岗位标题的前言/目录
            if "###" in part:
                # 极端情况：首段中本身有 ###，保守处理
                chunks.append(part.strip())
            continue
        chunk = "### " + part.strip()
        if len(chunk.strip()) < 20:
            continue
        chunks.append(chunk)
    return chunks


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    md_path = project_root / "doc" / "job_description.md"

    try:
        chunks = _load_md_chunks(md_path)
    except FileNotFoundError as exc:
        print(str(exc))
        sys.exit(1)

    if not chunks:
        print("未从 job_description.md 中解析到有效岗位块，取消入库。\n")
        return

    # 通过首块确定向量维度
    try:
        dim = len(embed(chunks[0]))
    except Exception as exc:
        print(f"首块 embedding 失败，无法确定向量维度: {exc}")
        sys.exit(1)
    if dim <= 0:
        print("embedding 结果维度为 0，取消入库。\n")
        return

    db = VectorDB()
    collection = "job_profiles"
    try:
        db.create_collection(collection, vector_size=dim, distance="Cosine")
    except Exception as exc:
        print(f"创建/检查集合 {collection!r} 失败: {exc}")
        sys.exit(1)

    # 批量写入（控制单次请求长度，避免总 token 过大）
    batch_size = 5
    total = 0
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        try:
            vectors = embed_batch(batch)
        except Exception as exc:
            print(f"批量 embedding 失败（索引区间 {start}:{start+len(batch)}）: {exc}")
            continue
        if len(vectors) != len(batch):
            print(f"embedding 返回数量与输入不一致，跳过该批：{start}:{start+len(batch)}\n")
            continue

        # Qdrant 当前集合配置要求 point ID 为无符号整数或 UUID，这里使用连续的整数 ID
        ids = list(range(start, start + len(batch)))
        payloads = []
        for chunk_idx, chunk in enumerate(batch):
            # 从首行提取 title（若存在）
            first_line = chunk.splitlines()[0].strip()
            title = first_line.lstrip("# ") if first_line.startswith("#") else first_line
            payloads.append(
                {
                    "text": chunk,
                    "source": "job_description.md",
                    "title": title,
                    "index": start + chunk_idx,
                }
            )
        try:
            db.upsert(collection, ids=ids, vectors=vectors, payloads=payloads)
        except Exception as exc:
            print(f"写入 Qdrant 失败（索引区间 {start}:{start+len(batch)}）: {exc}")
            continue
        total += len(batch)

    print(f"已将 {total} 个岗位块写入集合 {collection!r}。\n")


if __name__ == "__main__":
    main()

