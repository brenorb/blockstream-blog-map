"""Scrape every post on blog.blockstream.com (via the public sitemap).

Writes:
  data/raw/posts_full.jsonl  - metadata + body text (local only, not published)
  data/posts.json            - metadata only (titles, descriptions, tags, dates...)
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
CACHE = RAW / "html"
CACHE.mkdir(exist_ok=True)

SITEMAP = "https://blog.blockstream.com/sitemap-posts.xml"
HEADERS = {"User-Agent": "blockstream-blog-map/0.1 (personal research project)"}


def fetch(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    path = CACHE / f"{slug}.html"
    if path.exists():
        return path.read_text()
    for attempt in range(4):
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            path.write_text(r.text)
            time.sleep(0.25)  # be polite
            return r.text
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: HTTP {r.status_code}")


def meta(soup, key):
    tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
    return tag["content"].strip() if tag and tag.get("content") else None


def parse(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    ld = {}
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(s.string or "{}")
            if d.get("@type") == "Article":
                ld = d
        except json.JSONDecodeError:
            pass

    # Tags: names from ld+json keywords, slugs from <article class="post tag-...">
    tags = [t.strip() for t in (ld.get("keywords") or "").split(",") if t.strip()]
    tags = [t for t in tags if not t.startswith("#")]
    art = soup.find("article", class_="post") or soup.find("body")
    tag_slugs = [c[4:] for c in (art.get("class") or []) if c.startswith("tag-") and not c.startswith("tag-hash-")]

    authors = ld.get("author") or []
    if isinstance(authors, dict):
        authors = [authors]
    author_names = [a.get("name") for a in authors if a.get("name")]
    el = soup.select_one(".post-hero__author-names")
    if el and el.get_text(strip=True):
        names = [n.strip() for n in re.split(r",| and |&", el.get_text(" ", strip=True)) if n.strip()]
        if names:
            author_names = names

    body_el = soup.select_one(".post__content") or soup.select_one(".gh-content")
    body = body_el.get_text(" ", strip=True) if body_el else ""
    body = re.sub(r"\s+", " ", body)

    image = meta(soup, "og:image")
    return {
        "url": url,
        "slug": url.rstrip("/").rsplit("/", 1)[-1],
        "title": meta(soup, "og:title") or ld.get("headline") or soup.title.get_text(strip=True),
        "description": meta(soup, "og:description") or meta(soup, "description") or ld.get("description") or "",
        "published": meta(soup, "article:published_time") or ld.get("datePublished"),
        "modified": meta(soup, "article:modified_time") or ld.get("dateModified"),
        "tags": tags,
        "tag_slugs": tag_slugs,
        "primary_tag": tags[0] if tags else None,
        "authors": author_names,
        "image": image,
        "word_count": len(body.split()),
        "body": body,
    }


def main():
    xml = requests.get(SITEMAP, headers=HEADERS, timeout=30).text
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", xml) if "/content/images/" not in u]
    print(f"{len(urls)} post URLs")

    def work(u):
        try:
            return parse(u, fetch(u))
        except Exception as e:  # keep going, report at the end
            return {"url": u, "error": str(e)}

    with ThreadPoolExecutor(max_workers=4) as ex:
        posts = list(ex.map(work, urls))

    errors = [p for p in posts if "error" in p]
    posts = [p for p in posts if "error" not in p]
    posts.sort(key=lambda p: p["published"] or "")
    with open(RAW / "posts_full.jsonl", "w") as f:
        for p in posts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    public = [{k: v for k, v in p.items() if k != "body"} for p in posts]
    (ROOT / "data" / "posts.json").write_text(json.dumps(public, indent=1, ensure_ascii=False))
    print(f"saved {len(posts)} posts, {len(errors)} errors")
    for e in errors:
        print("  ERR", e["url"], e["error"])


if __name__ == "__main__":
    main()
