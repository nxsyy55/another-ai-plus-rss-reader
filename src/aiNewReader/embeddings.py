from __future__ import annotations

import struct

import httpx

from .config import get_config

_DIMS = 1024


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


async def embed_texts(texts: list[str]) -> list[list[float]]:
    cfg = get_config()
    base_url = cfg.provider.ollama_base_url
    model = cfg.provider.ollama_embed_model

    async with httpx.AsyncClient(timeout=60.0) as client:
        results: list[list[float]] = []
        for text in texts:
            resp = await client.post(
                f"{base_url}/api/embed",
                json={"model": model, "input": text},
            )
            resp.raise_for_status()
            data = resp.json()
            vec = data.get("embeddings", [data.get("embedding", [])])[0]
            results.append(vec)
        return results


async def embed_text(text: str) -> list[float]:
    results = await embed_texts([text])
    return results[0]


def pack_embedding(vec: list[float]) -> bytes:
    return _pack(vec)


def unpack_embedding(blob: bytes) -> list[float]:
    return _unpack(blob)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
