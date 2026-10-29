"""Embed every scraped post. Writes data/embeddings.npy (row order = data/posts.json)."""

import json

import numpy as np

from common import DATA, RAW, embed, post_text


def main():
    posts = [json.loads(l) for l in open(RAW / "posts_full.jsonl")]
    texts = [post_text(p["title"], p["description"], p["tags"], p["body"]) for p in posts]
    vecs = embed(texts)
    np.save(DATA / "embeddings.npy", vecs)
    print("embeddings", vecs.shape)


if __name__ == "__main__":
    main()
