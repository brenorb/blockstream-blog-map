"""Turn gap targets back into posts: embed each drafted candidate exactly like a real post,
measure where it lands, and keep the best candidate per hole.

A candidate is rejected if it is closer to an existing post than a typical post is to its
twin (it would be a near copy), or if it lands outside its hole on the 2D map.

Reads data/gaps.json, data/gap_targets.npy, data/ghost_drafts.json.
Writes data/ghosts.json, data/ghost_embeddings.npy, data/ghost_attempts.json.
"""

import json
import pickle

import numpy as np

from common import DATA, RAW, embed, place, post_text


def main():
    posts = json.load(open(DATA / "posts.json"))
    X = np.load(DATA / "embeddings.npy")
    gaps = json.load(open(DATA / "gaps.json"))
    T = np.load(DATA / "gap_targets.npy")
    drafts = json.load(open(DATA / "ghost_drafts.json"))
    proj = json.loads((RAW / "projection.json").read_text())
    reducer = pickle.load(open(RAW / "umap.pkl", "rb"))

    S = X @ X.T
    np.fill_diagonal(S, -1)
    nn_sim = S.max(1)
    median_twin = float(np.median(nn_sim))

    V = embed([post_text(d["title"], d["description"], d["tags"], d["lede"]) for d in drafts])
    land = place(reducer, V, proj)

    attempts = []
    for d, v, xy in zip(drafts, V, land):
        g = gaps[d["hole"]]
        sims = X @ v
        twin = float(sims.max())
        dist = float(np.linalg.norm(xy - np.array(g["center"])))
        a = {
            "hole": d["hole"],
            "title": d["title"],
            "cos_to_target": round(float(v @ T[d["hole"]]), 3),
            "twin": round(twin, 3),
            "twin_title": posts[int(sims.argmax())]["title"],
            "closer": round(float((nn_sim > twin).mean()), 4),
            "lands": [round(float(xy[0]), 4), round(float(xy[1]), 4)],
            "in_hole": dist <= g["radius"] * 1.25,
            "too_close": twin >= median_twin,
        }
        a["ok"] = a["in_hole"] and not a["too_close"]
        # prefer: on target, far from existing posts
        a["score"] = round(a["cos_to_target"] - 0.5 * twin + (0.2 if a["ok"] else 0), 4)
        attempts.append(a)

    ghosts, gvecs = [], []
    for h, g in enumerate(gaps):
        idx = [i for i, a in enumerate(attempts) if a["hole"] == h]
        print(f"\nH{h + 1} {g['name']}  (target twin {g['target_twin']})")
        for i in sorted(idx, key=lambda i: -attempts[i]["score"]):
            a = attempts[i]
            flag = "OK " if a["ok"] else ("NEAR" if a["too_close"] else "OUT")
            print(f"  [{flag}] cos→target {a['cos_to_target']:.3f}  twin {a['twin']:.3f} ({a['closer']*100:.1f}% closer)  "
                  f"in_hole={a['in_hole']}  {a['title'][:60]}")
            print(f"         twin: {a['twin_title'][:70]}")
        ok = [i for i in idx if attempts[i]["ok"]]
        if not ok:
            print("  !! no candidate passed; needs a rewrite")
            continue
        best = max(ok, key=lambda i: attempts[i]["score"])
        d, a = drafts[best], attempts[best]
        ing = [x["i"] for x in g["ingredients"]]
        ghosts.append({
            "id": f"idea-{len(ghosts) + 1}",
            "region": g["name"],
            "title": d["title"],
            "description": d["description"],
            "lede": d["lede"],
            "tags": d["tags"],
            "why": d["why"],
            "ingredients": ing,
            "ingredient_sims": {str(j): round(float(X[j] @ V[best]), 3) for j in ing},
            "hole": {"x": g["center"][0], "y": g["center"][1], "r": g["radius"]},
            "cos_to_target": a["cos_to_target"],
            "candidates_tried": len(idx),
            "method": (
                f"Hole of radius {g['radius']:.2f} seen in the map screenshot between {', '.join(g['topics'])}. "
                f"Blended {len(ing)} posts from its rim, then pushed the blend away from all {len(posts)} posts on the "
                f"1024-dim sphere (nearest-post similarity {g['blend_twin']:.2f} → {g['target_twin']:.2f}). "
                f"Wrote {len(idx)} candidate posts for that point, embedded each with the same model, and kept the one "
                f"closest to the target (cosine {a['cos_to_target']:.2f}) that lands in the hole and is not a near copy."
            ),
        })
        gvecs.append(V[best])

    (DATA / "ghost_attempts.json").write_text(json.dumps(attempts, indent=1, ensure_ascii=False))
    (DATA / "ghosts.json").write_text(json.dumps(ghosts, indent=1, ensure_ascii=False))
    np.save(DATA / "ghost_embeddings.npy", np.array(gvecs, dtype=np.float32))
    print(f"\nmedian twin of real posts: {median_twin:.3f}; kept {len(ghosts)} ghosts")


if __name__ == "__main__":
    main()
