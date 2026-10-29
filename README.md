# Blockstream Blog Map

An interactive map of every post on [blog.blockstream.com](https://blog.blockstream.com/), placed by meaning, plus generated "new idea" posts for the empty spots between topics.

**Live map:** https://brenorb.com/blockstream-blog-map/

![Map](analysis/map-after.png)

Inspired by [this video](https://x.com/re_skob/status/2113043120128483349), which did the same thing for every game on Steam.

## How it works

1. **Scrape** – `scripts/scrape.py` reads the blog's public sitemap and pulls each post's title, description, tags, authors, dates and opening text.
2. **Embed** – `scripts/embed.py` turns each post into 1024 numbers with the open-weights model [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) (Apache-2.0). The embedded text is the title, description, tags and the first 200 words.
3. **Map** – `scripts/build_map.py` groups posts into 14 topics (k-means), lays them out in 2D with UMAP (cosine), and records each post's nearest neighbors and how lonely it is.
4. **Site** – `docs/` is a static page (canvas + d3-zoom) served by GitHub Pages.
5. **Find holes** – `scripts/find_gaps.py`. Holes were first spotted by eye in a screenshot of the live map ([`analysis/map-before.png`](analysis/map-before.png)), then snapped to empty circles of the Delaunay triangulation of the 2D layout. Every hole is ranked by size and by how related the posts on its rim are ([`analysis/holes.png`](analysis/holes.png)).
6. **Pick a point in embedding space** – for each hole, the posts on its rim are averaged (the "blend"). The blend is then pushed away from all 335 posts by gradient ascent on the unit sphere: minimize a smooth max of cosine similarity to every post, while staying within cosine 0.86 of the blend so the point stays specific instead of drifting into generic mush. This lowers the nearest-post similarity from 0.82–0.90 to 0.67–0.76.
7. **Turn the point back into a post** – `scripts/ghosts.py`. Each target is "read" through its nearest posts and the tags it leans toward. Candidate posts are written for it (`data/ghost_drafts.json`), and each candidate is embedded exactly like a real post. A candidate is kept only if it lands inside its hole on the 2D map and is further from every real post than a typical post is from its own twin (0.775). Weak holes got a second round of drafts. The best candidate per hole is drawn on the map as a gold star.

## The generated ideas

Twenty-four candidate posts were tried for six holes; all scores are in `data/ghost_attempts.json`. These six were kept:

| # | Idea | Hole | Cos to target | Closest real post (sim) | Real posts with a closer twin |
|---|---|---|---|---|---|
| 1 | [Smart Contracts as Lightning Endpoints: Paying Liquid Contracts over Lightning](https://brenorb.com/blockstream-blog-map/#idea-1) | Void below Covenants & Elements | 0.66 | Enabling Lightning Payments with Liquid Swaps in the Blockstream App (0.70) | 74% |
| 2 | [Hiding the Policy and the Amount: Designing a Fully Private Taproot Wallet](https://brenorb.com/blockstream-blog-map/#idea-2) | Pocket between Green, Signatures & Federations | 0.67 | PSET: Constructing Confidential Transactions (0.67) | 86% |
| 3 | [Lightning for Shops Without Running a Node](https://brenorb.com/blockstream-blog-map/#idea-3) | Strip between Liquid Assets & Lightning | 0.64 | Enabling Lightning Payments with Liquid Swaps in the Blockstream App (0.72) | 68% |
| 4 | [An Interop Scorecard for Bitcoin Layers](https://brenorb.com/blockstream-blog-map/#idea-4) | Gap between Explorer, Liquid & the data-feed island | 0.54 | Increasing Interoperability Between Bitcoin’s Second-Layer Protocols (0.66) | 87% |
| 5 | [Clear Signing for Simplicity: Teaching a Hardware Wallet to Read Contracts](https://brenorb.com/blockstream-blog-map/#idea-5) | Edge between Simplicity & Signatures | 0.63 | Welcome to the New Simplicity \| Blockstream (0.73) | 64% |
| 6 | [A Self-Custody Workshop in a Box](https://brenorb.com/blockstream-blog-map/#idea-6) | Gap between Jade & Green Wallet | 0.64 | Blockstream Local: Now Powered by the Blockstream App (0.69) | 80% |

"Cos to target" is how close the written post's embedding is to the chosen point. For comparison, the posts the point was blended from sit at about 0.6–0.7 from it.

## Run it

```bash
uv sync
cd scripts
uv run python scrape.py
uv run python embed.py
uv run python build_map.py   # map without ideas
uv run python find_gaps.py   # holes + target points
uv run python ghosts.py      # score drafts in data/ghost_drafts.json
uv run python build_map.py   # map with ideas
python3 -m http.server -d ../docs 8765
```

## Notes

- Only titles, descriptions and metadata are published in `docs/data.json`. Post bodies stay in the git-ignored `data/raw/`.
- One post on the blog, `/reducing-bitcoin-transaction-sizes-with-x-only-pubkeys-2/`, has the c-lightning 0.7.3 text under the x-only pubkeys title. It's kept as published.
- The generated ideas are not Blockstream posts and make no claims about Blockstream's plans.
- Not affiliated with Blockstream.
