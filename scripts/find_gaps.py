"""Find holes in the map and pick target points in embedding space for them.

1. 2D holes: largest empty circles (Voronoi vertices) that have posts on every side
   and sit between at least two topics.
2. For each hole, blend the embeddings of the posts around it (the "ingredients"),
   then push that blend away from every existing post with gradient ascent on the
   unit sphere, while keeping it close to the blend so it stays specific.
3. "Read" each target point: nearest posts, tags it leans toward, key terms.

Writes data/gaps.json and data/gap_targets.npy, plus analysis/holes.png.
"""

import json
import pickle
from collections import Counter

import numpy as np
import torch
from scipy.spatial import Delaunay

from common import DATA, RAW, ROOT, place

N_HOLES = 6

# Holes spotted by eye in analysis/map-before.png (1600x1000 screenshot of the live site), in pixels.
SCREENSHOT = (1600, 1000)
SCREENSHOT_HOLES = {
    "Void below Covenants & Elements": (905, 640),
    "Pocket between Green, Signatures & Federations": (680, 430),
    "Strip between Liquid Assets & Lightning": (1080, 630),
    "Gap between Explorer, Liquid & the data-feed island": (1050, 360),
    "Edge between Simplicity & Signatures": (420, 610),
    "Gap between Jade & Green Wallet": (600, 215),
}
BETA = 40.0          # softmax sharpness for "distance to nearest post"
STAY = 0.86          # min cosine to the ingredient blend (keeps the idea specific)
STEPS = 400


def circumcircle(a, b, c):
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None, np.inf
    ux = ((a @ a) * (b[1] - c[1]) + (b @ b) * (c[1] - a[1]) + (c @ c) * (a[1] - b[1])) / d
    uy = ((a @ a) * (c[0] - b[0]) + (b @ b) * (a[0] - c[0]) + (c @ c) * (b[0] - a[0])) / d
    o = np.array([ux, uy])
    return o, float(np.linalg.norm(a - o))


def rim_ingredients(xy, labels, center, r, corners, max_n=6):
    """Posts on the rim of the hole: the triangle corners first, then nearby rim posts, at most 2 per topic."""
    d = np.linalg.norm(xy - center, axis=1)
    order = list(corners) + [int(j) for j in np.argsort(d) if d[j] <= r * 1.35 and j not in corners]
    per, out = Counter(), []
    for j in order:
        if per[labels[j]] < 2:
            out.append(int(j))
            per[labels[j]] += 1
        if len(out) == max_n:
            break
    return out


def screenshot_to_map(px, py, xy):
    """Invert the site's layout (docs/app.js resize()) for the screenshot size."""
    W, H = SCREENSHOT
    x0, x1 = xy[:, 0].min(), xy[:, 0].max()
    y0, y1 = xy[:, 1].min(), xy[:, 1].max()
    pad_top, pad_bottom = 130, 50
    aw, ah = W - 60, H - pad_top - pad_bottom
    k = min(aw / (x1 - x0), ah / (y1 - y0))
    bx, by = W / 2 - k * (x0 + x1) / 2, pad_top + ah / 2 + k * (y0 + y1) / 2
    return np.array([(px - bx) / k, (by - py) / k])


def find_holes(xy, labels, X):
    """Empty circles of the Delaunay triangulation (empty by construction) whose center is inside the
    map and whose corner posts surround it. Ranked by size and by how related the rim posts are,
    so we prefer big holes between topics that actually belong together."""
    tri = Delaunay(xy)
    cands = []
    for simplex in tri.simplices:
        a, b, c = xy[simplex]
        o, r = circumcircle(a, b, c)
        if o is None or tri.find_simplex(o) < 0:
            continue  # center outside the map's convex hull
        ang = np.sort(np.arctan2(xy[simplex, 1] - o[1], xy[simplex, 0] - o[0]))
        # corner posts all on one side = an open bay rather than a hole
        surrounded = np.diff(np.concatenate([ang, [ang[0] + 2 * np.pi]])).max() <= np.deg2rad(200)
        ing = rim_ingredients(xy, labels, o, r, list(simplex))
        if len(set(labels[ing].tolist())) < 2:
            continue  # inside one topic, not between topics
        E = X[ing]
        G = E @ E.T
        coherence = float((G.sum() - len(ing)) / (len(ing) * (len(ing) - 1)))
        cands.append({"r": r, "center": o, "ingredients": ing, "coherence": coherence, "surrounded": bool(surrounded)})
    for c in cands:
        c["score"] = c["r"] ** 1.5 * max(c["coherence"] - 0.42, 0)
    cands.sort(key=lambda c: -c["score"])
    for rank, c in enumerate(cands):
        c["rank"] = rank
    return cands


def top_holes(cands):
    chosen = []
    for c in (c for c in cands if c["surrounded"]):
        if all(np.linalg.norm(c["center"] - k["center"]) > max(c["r"], k["r"]) for k in chosen):
            chosen.append(c)
        if len(chosen) == N_HOLES:
            break
    return chosen


def push_away(X, v0, ingredients):
    Xt = torch.tensor(X)
    anchor = torch.tensor(v0)
    v = anchor.clone().requires_grad_(True)
    opt = torch.optim.Adam([v], lr=0.01)
    for _ in range(STEPS):
        u = v / v.norm()
        sims = Xt @ u
        crowd = torch.logsumexp(BETA * sims, 0) / BETA        # smooth "max similarity to any post"
        drift = torch.relu(STAY - u @ anchor)                  # stay near the blend
        loss = crowd + 20 * drift ** 2 * 100
        opt.zero_grad()
        loss.backward()
        opt.step()
    u = (v / v.norm()).detach().numpy()
    return u.astype(np.float32)


def read_point(u, X, posts, tag_vecs, k=10):
    sims = X @ u
    order = np.argsort(-sims)[:k]
    tags = sorted(((float(tv @ u), t) for t, tv in tag_vecs.items()), reverse=True)[:6]
    return {
        "nearest": [{"i": int(j), "sim": round(float(sims[j]), 3), "title": posts[j]["title"]} for j in order],
        "lean_tags": [t for _, t in tags],
        "twin": float(sims[order[0]]),
    }


def main():
    posts = json.load(open(DATA / "posts.json"))
    X = np.load(DATA / "embeddings.npy")
    xy = np.load(RAW / "map_xy.npy")
    labels = np.load(RAW / "labels.npy")
    names = {int(k): v["name"] for k, v in json.load(open(DATA / "cluster_names.json")).items()}
    proj = json.loads((RAW / "projection.json").read_text())
    reducer = pickle.load(open(RAW / "umap.pkl", "rb"))

    S = X @ X.T
    np.fill_diagonal(S, -1)
    nn_sim = S.max(1)

    tag_posts = {}
    for i, p in enumerate(posts):
        for t in p["tags"]:
            tag_posts.setdefault(t, []).append(i)
    tag_vecs = {t: X[ix].mean(0) / np.linalg.norm(X[ix].mean(0)) for t, ix in tag_posts.items() if len(ix) >= 3}

    cands = find_holes(xy, labels, X)
    algo = top_holes(cands)
    # Snap each hole seen in the screenshot to the largest empty circle that covers that spot.
    holes = []
    for name, (px, py) in SCREENSHOT_HOLES.items():
        p = screenshot_to_map(px, py, xy)
        covering = [c for c in cands if np.linalg.norm(c["center"] - p) <= c["r"]]
        if not covering:
            print(f"  (no empty circle covers '{name}' at {p.round(3)})")
            continue
        enclosed = [c for c in covering if c["surrounded"]]
        best = max(enclosed, key=lambda c: c["r"]) if enclosed else max(covering, key=lambda c: c["score"])
        if any(np.linalg.norm(best["center"] - h["center"]) < 1e-6 for h in holes):
            continue
        best = {**best, "name": name, "seen_at_px": [px, py]}
        best["also_top_algorithmic"] = any(np.linalg.norm(best["center"] - a["center"]) < max(best["r"], a["r"]) for a in algo)
        holes.append(best)
    print("algorithmic top holes:", [(a["center"].round(2).tolist(), round(a["r"], 3)) for a in algo])
    out, targets = [], []
    for h, hole in enumerate(holes):
        r, c, ingredients = hole["r"], hole["center"], hole["ingredients"]
        blend = X[ingredients].mean(0)
        blend /= np.linalg.norm(blend)
        u = push_away(X, blend, ingredients)
        land = place(reducer, u[None], proj)[0]
        reading = read_point(u, X, posts, tag_vecs)
        blend_twin = float((X @ blend).max())
        entry = {
            "hole": h,
            "name": hole["name"],
            "seen_at_px": hole["seen_at_px"],
            "rank": hole["rank"],
            "also_top_algorithmic": hole["also_top_algorithmic"],
            "surrounded": hole["surrounded"],
            "center": [round(float(c[0]), 4), round(float(c[1]), 4)],
            "radius": round(float(r), 4),
            "topics": sorted({names[int(labels[j])] for j in ingredients}),
            "coherence": round(hole["coherence"], 3),
            "ingredients": [{"i": j, "title": posts[j]["title"], "topic": names[int(labels[j])], "sim_to_target": round(float(X[j] @ u), 3)} for j in ingredients],
            "blend_twin": round(blend_twin, 3),
            "target_twin": round(reading["twin"], 3),
            "target_closer": round(float((nn_sim > reading["twin"]).mean()), 4),
            "target_cos_blend": round(float(u @ blend), 3),
            "target_lands_at": [round(float(land[0]), 4), round(float(land[1]), 4)],
            "lands_in_hole": bool(np.linalg.norm(land - c) <= r * 1.5),
            **{k: v for k, v in reading.items() if k != "twin"},
        }
        out.append(entry)
        targets.append(u)
        print(f"\nHOLE {h} [{hole['name']}] rank={hole['rank']} top6={hole['also_top_algorithmic']} r={r:.3f} coherence={hole['coherence']:.3f} at {c.round(3)}  topics={entry['topics']}")
        print(f"  blend twin {blend_twin:.3f} -> pushed twin {reading['twin']:.3f} "
              f"({entry['target_closer']*100:.1f}% of posts have a closer twin), cos to blend {u @ blend:.3f}, "
              f"lands {land.round(3)} in_hole={entry['lands_in_hole']}")
        print("  ingredients:", " | ".join(f"{posts[j]['title'][:45]}" for j in ingredients))
        print("  leans toward tags:", reading["lean_tags"])
        for n in reading["nearest"][:5]:
            print(f"    {n['sim']:.3f} {n['title'][:80]}")

    (DATA / "gaps.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    np.save(DATA / "gap_targets.npy", np.array(targets))
    plot(xy, labels, names, out)


def plot(xy, labels, names, holes):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 9), facecolor="#05070c")
    ax.set_facecolor("#05070c")
    cmap = plt.get_cmap("tab20")
    ax.scatter(xy[:, 0], xy[:, 1], c=[cmap(l % 20) for l in labels], s=14, alpha=0.9, linewidths=0)
    for c in np.unique(labels):
        m = xy[labels == c].mean(0)
        ax.text(m[0], m[1], names[int(c)], color=cmap(c % 20), fontsize=8, ha="center", alpha=0.9)
    for h in holes:
        cx, cy = h["center"]
        ax.add_patch(plt.Circle((cx, cy), h["radius"], fill=False, ls="--", color="#ffb347", lw=1.2))
        ax.text(cx, cy, f"H{h['hole'] + 1}", color="#ffb347", ha="center", va="center", fontsize=11, weight="bold")
        lx, ly = h["target_lands_at"]
        ax.plot([cx, lx], [cy, ly], color="#ffb347", lw=0.6, alpha=0.6)
        ax.scatter([lx], [ly], marker="*", s=120, color="#ffb347")
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Holes in the Blockstream blog map (dashed) and where each pushed target lands (stars)", color="#cfd6e2")
    (ROOT / "analysis").mkdir(exist_ok=True)
    fig.savefig(ROOT / "analysis" / "holes.png", dpi=110, bbox_inches="tight", facecolor="#05070c")


if __name__ == "__main__":
    main()
