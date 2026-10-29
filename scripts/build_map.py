"""Project embeddings to 2D, cluster them, compute neighbors, and export docs/data.json.

Also exports ghost (generated) posts from data/ghosts.json and data/marked_ghosts.json if present.
"""

import json
import pickle
from collections import Counter

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from common import DATA, RAW, SITE, place

N_CLUSTERS = 14
K_NEIGHBORS = 8


def fit_umap(X):
    import umap

    reducer = umap.UMAP(n_neighbors=15, min_dist=0.12, metric="cosine", random_state=42)
    Y = reducer.fit_transform(X)
    with open(RAW / "umap.pkl", "wb") as f:
        pickle.dump(reducer, f)
    return reducer, Y


def cluster_terms(posts, labels, k):
    docs = [" ".join(posts[i]["title"] + " " + posts[i]["description"] for i in np.where(labels == c)[0]) for c in range(k)]
    tf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_df=0.5, min_df=1, token_pattern=r"[A-Za-z][A-Za-z0-9\-]+")
    M = tf.fit_transform(docs).toarray()
    vocab = np.array(tf.get_feature_names_out())
    return [list(vocab[np.argsort(-M[c])[:6]]) for c in range(k)]


def main():
    posts = json.load(open(DATA / "posts.json"))
    X = np.load(DATA / "embeddings.npy")
    n = len(posts)

    S = X @ X.T
    np.fill_diagonal(S, -1)
    nn_idx = np.argsort(-S, axis=1)[:, :K_NEIGHBORS]
    nn_sim = S[np.arange(n), nn_idx[:, 0]]
    # loneliness: share of posts whose nearest twin is closer than this post's nearest twin
    closer = np.array([(nn_sim > s).mean() for s in nn_sim])

    labels = KMeans(N_CLUSTERS, n_init=20, random_state=0).fit_predict(X)
    # order clusters by mean date so colors run roughly old -> new
    names_path = DATA / "cluster_names.json"
    terms = cluster_terms(posts, labels, N_CLUSTERS)
    names = json.load(open(names_path)) if names_path.exists() else {}

    reducer, Y = fit_umap(X)
    center = Y.mean(0)
    scale = float(np.abs(Y - center).max())
    Yn = (Y - center) / scale
    (RAW / "projection.json").write_text(json.dumps({"center": center.tolist(), "scale": scale}))
    np.save(RAW / "map_xy.npy", Yn)

    clusters = []
    for c in range(N_CLUSTERS):
        idx = np.where(labels == c)[0]
        tags = Counter(t for i in idx for t in posts[i]["tags"]).most_common(3)
        clusters.append({
            "id": c,
            "name": names.get(str(c), {}).get("name") or ", ".join(terms[c][:3]),
            "blurb": names.get(str(c), {}).get("blurb", ""),
            "size": int(len(idx)),
            "terms": terms[c],
            "top_tags": [t for t, _ in tags],
            "x": float(Yn[idx, 0].mean()),
            "y": float(Yn[idx, 1].mean()),
            "typical_twin": float(np.median(nn_sim[idx])),
            "examples": [posts[i]["title"] for i in idx[np.argsort(-nn_sim[idx])][:4]],
        })

    out_posts = []
    for i, p in enumerate(posts):
        out_posts.append({
            "i": i,
            "title": p["title"],
            "description": p["description"] if p["description"] != p["title"] else "",
            "url": p["url"],
            "date": (p["published"] or "")[:10],
            "tags": p["tags"],
            "authors": p["authors"],
            "image": p["image"],
            "words": p["word_count"],
            "cluster": int(labels[i]),
            "x": round(float(Yn[i, 0]), 5),
            "y": round(float(Yn[i, 1]), 5),
            "nn": [[int(j), round(float(S[i, j]), 3)] for j in nn_idx[i]],
            "twin": round(float(nn_sim[i]), 3),
            "closer": round(float(closer[i]), 4),
        })

    # Ghost (generated) posts: placed with the same UMAP model and measured the same way as real posts.
    ghosts = []
    # ghosts.json: holes found by math (find_gaps.py); marked_ghosts.json: spots marked by hand (marked.py)
    gmeta, gvecs = [], []
    for name, vec in (("ghosts.json", "ghost_embeddings.npy"), ("marked_ghosts.json", "marked_embeddings.npy")):
        if (DATA / name).exists() and (DATA / vec).exists():
            gmeta += json.load(open(DATA / name))
            gvecs.append(np.load(DATA / vec))
    if gmeta:
        G = np.vstack(gvecs)
        gxy = place(reducer, G, {"center": center, "scale": scale})
        for gi, g in enumerate(gmeta):
            if "mark" in g:  # draw the hand-marked target the same way as a hole
                g = {**g, "hole": g["mark"]}
            sims = X @ G[gi]
            order = np.argsort(-sims)[:K_NEIGHBORS]
            ghosts.append({
                **{k: v for k, v in g.items() if k not in ("lede_for_embedding",)},
                "x": round(float(gxy[gi, 0]), 5),
                "y": round(float(gxy[gi, 1]), 5),
                "nn": [[int(j), round(float(sims[j]), 3)] for j in order],
                "twin": round(float(sims[order[0]]), 3),
                "closer": round(float((nn_sim > sims[order[0]]).mean()), 4),
            })

    data = {
        "generated": __import__("datetime").date.today().isoformat(),
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "stats": {
            "n": n,
            "median_twin": float(np.median(nn_sim)),
            "p5_twin": float(np.percentile(nn_sim, 5)),
            "p95_twin": float(np.percentile(nn_sim, 95)),
            "years": [posts[0]["published"][:4], posts[-1]["published"][:4]],
        },
        "clusters": clusters,
        "posts": out_posts,
        "ghosts": ghosts,
    }
    SITE.mkdir(exist_ok=True)
    (SITE / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    np.save(RAW / "labels.npy", labels)

    print(f"wrote {SITE/'data.json'}  posts={n} clusters={N_CLUSTERS}")
    for c in clusters:
        print(f"[{c['id']:2}] n={c['size']:3} twin={c['typical_twin']:.2f} {c['top_tags']} | {', '.join(c['terms'])}")
        for t in c["examples"][:3]:
            print("       -", t[:80])


if __name__ == "__main__":
    main()
