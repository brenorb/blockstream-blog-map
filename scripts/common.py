"""Shared helpers: one embedding model and one text format for real and generated posts."""

from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
SITE = ROOT / "docs"

MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"  # open weights, Apache-2.0, 1024 dims
LEDE_WORDS = 200


def post_text(title: str, description: str, tags: list[str], lede: str) -> str:
    """The exact text that gets embedded. Same format for real and generated posts."""
    lede = " ".join(lede.split()[:LEDE_WORDS])
    parts = [title.strip()]
    if description and description.strip() != title.strip():
        parts.append(description.strip())
    if tags:
        parts.append("Topics: " + ", ".join(tags))
    parts.append(lede)
    return "\n".join(parts)


@lru_cache(maxsize=1)
def model():
    import torch
    from sentence_transformers import SentenceTransformer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    m = SentenceTransformer(MODEL_NAME, device=device)
    m.max_seq_length = 512
    return m


def embed(texts: list[str]) -> np.ndarray:
    v = model().encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=len(texts) > 32)
    return np.asarray(v, dtype=np.float32)
