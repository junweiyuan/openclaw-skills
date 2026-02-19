#!/usr/bin/env python3
"""
Grab latest tweets via Nitter RSS and produce a quick summary.

Usage:
  python3 scripts/twitter_summary.py --user karpathy --limit 8
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "just", "about",
    "your", "you", "are", "was", "were", "will", "would", "can", "could", "they",
    "them", "their", "our", "out", "into", "not", "but", "get", "got", "all", "more",
    "how", "what", "when", "why", "who", "http", "https", "www", "com", "amp",
}


@dataclass
class Tweet:
    title: str
    link: str
    published: datetime


def fetch(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def clean_text(s: str) -> str:
    s = html.unescape(s)
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_rss(xml_bytes: bytes) -> list[Tweet]:
    root = ET.fromstring(xml_bytes)
    items = root.findall("./channel/item")
    out: list[Tweet] = []
    for item in items:
        title = clean_text(item.findtext("title", default=""))
        link = item.findtext("link", default="")
        pub = item.findtext("pubDate", default="")
        try:
            published = parsedate_to_datetime(pub).astimezone(timezone.utc)
        except Exception:
            published = datetime.now(tz=timezone.utc)
        if title:
            out.append(Tweet(title=title, link=link, published=published))
    return out


def fetch_tweets(user: str, limit: int) -> tuple[str, list[Tweet]]:
    err_msgs = []
    for base in NITTER_INSTANCES:
        url = f"{base}/{urllib.parse.quote(user)}/rss"
        try:
            raw = fetch(url)
            tweets = parse_rss(raw)
            if tweets:
                return base, tweets[:limit]
            err_msgs.append(f"{base}: empty feed")
        except Exception as e:
            err_msgs.append(f"{base}: {e}")
    raise RuntimeError("All instances failed: " + " | ".join(err_msgs))


def extract_keywords(tweets: list[Tweet], topn: int = 8) -> list[str]:
    words: list[str] = []
    for t in tweets:
        for w in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", t.title.lower()):
            if w not in STOPWORDS and not w.startswith("tco"):
                words.append(w)
    return [w for w, _ in Counter(words).most_common(topn)]


def build_summary(user: str, src: str, tweets: list[Tweet]) -> str:
    kws = extract_keywords(tweets)
    lines = []
    lines.append(f"@{user} 最新 {len(tweets)} 条推文摘要")
    lines.append(f"数据源: {src}")
    if kws:
        lines.append("高频关键词: " + ", ".join(kws))
    lines.append("\n要点:")

    for i, t in enumerate(tweets[:5], start=1):
        short = textwrap.shorten(t.title, width=120, placeholder="…")
        ts = t.published.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"{i}. [{ts}] {short}")
        lines.append(f"   {t.link}")

    lines.append("\n一句话总结:")
    if kws:
        lines.append("最近内容主要围绕 " + " / ".join(kws[:4]) + "，以短观点和链接分享为主。")
    else:
        lines.append("最近推文以动态更新和短观点为主。")

    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch latest tweets and summarize.")
    p.add_argument("--user", required=True, help="X username without @")
    p.add_argument("--limit", type=int, default=8, help="How many latest tweets to read")
    args = p.parse_args()

    user = args.user.lstrip("@")
    limit = max(1, min(args.limit, 30))

    try:
        src, tweets = fetch_tweets(user, limit)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(build_summary(user, src, tweets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
