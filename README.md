# Blockstream Blog Map

An interactive map of every post on [blog.blockstream.com](https://blog.blockstream.com/), placed by meaning, plus generated "new idea" posts for the empty spots between topics.

**Live map:** https://brenorb.github.io/blockstream-blog-map/

Inspired by [this video](https://x.com/re_skob/status/2113043120128483349), which did the same thing for every game on Steam.

## How it works

1. **Scrape** – `scripts/scrape.py` reads the blog's public sitemap and pulls each post's title, description, tags, authors, dates and opening text.
2. **Embed** – `scripts/embed.py` turns each post into 1024 numbers with the open-weights model [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) (Apache-2.0). The embedded text is the title, description, tags and the first 200 words.
3. **Map** – `scripts/build_map.py` groups posts into 14 topics (k-means), lays them out in 2D with UMAP (cosine), and records each post's nearest neighbors and how lonely it is.
4. **Site** – `docs/` is a static page (canvas + d3-zoom) served by GitHub Pages.

## Run it

```bash
uv sync
cd scripts
uv run python scrape.py
uv run python embed.py
uv run python build_map.py
python3 -m http.server -d ../docs 8765
```

## Notes

- Only titles, descriptions and metadata are published in `docs/data.json`. Post bodies stay in the git-ignored `data/raw/`.
- One post on the blog, `/reducing-bitcoin-transaction-sizes-with-x-only-pubkeys-2/`, has the c-lightning 0.7.3 text under the x-only pubkeys title. It's kept as published.
- Not affiliated with Blockstream.
