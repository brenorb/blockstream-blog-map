"""Fill the spots marked by hand on a screenshot of the live map.

The marks were drawn on a 2x screenshot of the live site. The six gold stars in that same
screenshot have known map positions, so a straight-line fit turns pixels into map coordinates
(see data/user_marks.json; the fit is accurate to about one pixel).

For each mark, every drafted post is embedded like a real post and placed on the map. A draft
is kept if it lands close to the mark (within half the gap to the nearest real post, at least
0.04) and is not a near copy of an existing post (nearest-post similarity below the median twin).
Among those, the one that lands closest wins.

Reads data/user_marks.json, data/marked_drafts.json.
Writes data/marked_attempts.json, data/marked_ghosts.json, data/marked_embeddings.npy.
"""

import json
import pickle
import sys

import numpy as np

from common import DATA, RAW, embed, place, post_text


def tolerance(nearest: float) -> float:
    return max(0.5 * nearest, 0.04)


def main(only=None):
    posts = json.load(open(DATA / "posts.json"))
    X = np.load(DATA / "embeddings.npy")
    xy = np.load(RAW / "map_xy.npy")
    marks = json.load(open(DATA / "user_marks.json"))["marks"]
    drafts = json.load(open(DATA / "marked_drafts.json"))
    if only:
        drafts = [d for d in drafts if str(d["mark"]) in only]
    proj = json.loads((RAW / "projection.json").read_text())
    reducer = pickle.load(open(RAW / "umap.pkl", "rb"))

    S = X @ X.T
    np.fill_diagonal(S, -1)
    nn_sim = S.max(1)
    median_twin = float(np.median(nn_sim))

    V = embed([post_text(d["title"], d["description"], d["tags"], d["lede"]) for d in drafts])
    land = place(reducer, V, proj)

    attempts = []
    for d, v, L in zip(drafts, V, land):
        mk = marks[str(d["mark"])]
        c = np.array([mk["x"], mk["y"]])
        sims = X @ v
        top = np.argsort(-sims)[:5]
        off = float(np.linalg.norm(L - c))
        a = {
            "mark": d["mark"],
            "title": d["title"],
            "lands": [round(float(L[0]), 4), round(float(L[1]), 4)],
            "off": round(off, 4),
            "miss": [round(float(L[0] - c[0]), 3), round(float(L[1] - c[1]), 3)],
            "tol": round(tolerance(mk["nearest"]), 4),
            "twin": round(float(sims.max()), 3),
            "twin_title": posts[int(top[0])]["title"],
            "pulls": [
                {"title": posts[j]["title"], "sim": round(float(sims[j]), 3),
                 "dx": round(float(xy[j, 0] - c[0]), 2), "dy": round(float(xy[j, 1] - c[1]), 2)}
                for j in top
            ],
        }
        a["ok"] = off <= a["tol"] and a["twin"] < median_twin
        attempts.append((a, d, v))

    if only:  # quick look at a subset; don't overwrite outputs
        report(attempts, marks)
        return

    report(attempts, marks)
    ghosts, gvecs = [], []
    existing = json.load(open(DATA / "ghosts.json"))
    for m in sorted(marks, key=int):
        ok = [t for t in attempts if str(t[0]["mark"]) == m and t[0]["ok"]]
        if not ok:
            print(f"!! mark {m}: nothing passed")
            continue
        a, d, v = min(ok, key=lambda t: t[0]["off"])
        mk = marks[m]
        tried = sum(1 for t in attempts if str(t[0]["mark"]) == m)
        ghosts.append({
            "id": f"idea-{len(existing) + len(ghosts) + 1}",
            "region": f"Spot {m} marked by hand on the map",
            "title": d["title"],
            "description": d["description"],
            "lede": d["lede"],
            "tags": d["tags"],
            "why": d["why"],
            "picked_by": "hand",
            "mark": {"x": mk["x"], "y": mk["y"], "r": a["tol"]},
            "lands_off": a["off"],
            "candidates_tried": tried,
            "method": (
                f"Spot marked by hand on a screenshot of the map. Wrote {tried} candidate posts mixing the "
                f"topics around it, embedded each with the same model and placed it on the map. Kept the one "
                f"that lands closest to the mark ({a['off']:.3f} away, allowed {a['tol']:.3f}) and is not a near "
                f"copy of an existing post (closest real post {a['twin']:.2f}, typical twin {median_twin:.2f})."
            ),
        })
        gvecs.append(v)

    (DATA / "marked_attempts.json").write_text(
        json.dumps([t[0] for t in attempts], indent=1, ensure_ascii=False))
    (DATA / "marked_ghosts.json").write_text(json.dumps(ghosts, indent=1, ensure_ascii=False))
    np.save(DATA / "marked_embeddings.npy", np.array(gvecs, dtype=np.float32))
    print(f"\nmedian twin {median_twin:.3f}; kept {len(ghosts)} of {len(marks)} marks")


def report(attempts, marks):
    for m in sorted(marks, key=int):
        rows = sorted([t[0] for t in attempts if str(t[0]["mark"]) == m], key=lambda a: a["off"])
        if not rows:
            continue
        print(f"\n== mark {m}  (tolerance {rows[0]['tol']:.3f})")
        for a in rows:
            flag = "OK  " if a["ok"] else ("NEAR" if a["off"] <= a["tol"] else "OFF ")
            print(f"  [{flag}] off {a['off']:.3f} ({a['miss'][0]:+.2f},{a['miss'][1]:+.2f})  twin {a['twin']:.3f}  {a['title'][:70]}")
            print("         pulls: " + " | ".join(
                f"{p['title'][:28]} ({p['dx']:+.2f},{p['dy']:+.2f})" for p in a["pulls"][:3]))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
