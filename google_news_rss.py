"""
Google News RSS Fetcher

Builds Google News RSS URLs (top headlines or search), fetches the feed
with a configurable User-Agent, parses items, and prints a concise list.
Optionally saves results to JSON.

No external dependencies; uses Python standard library.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional

# -----------------------------
# Configuration
# -----------------------------
# Mode: 'search' for keyword search, 'topic' for a built-in Google News topic,
# or 'custom' to use FEED_URL directly
MODE: str = "search"  # options: 'search' | 'topic' | 'custom'

# Region and language (Google News parameters)
HL: str = "en-US"  # UI language
GL: str = "US"     # Country/Geolocation
CEID: str = "US:en"  # Country:language (often GL:lang)

# Search configuration (used when MODE == 'search')
SEARCH_QUERY: str = "AI technology"  # Example query; URL-encoded automatically

# Topic configuration (used when MODE == 'topic')
# Examples (case-insensitive): 'WORLD', 'NATION', 'BUSINESS', 'TECHNOLOGY',
# 'ENTERTAINMENT', 'SCIENCE', 'SPORTS', 'HEALTH'
TOPIC: str = "TECHNOLOGY"

# Custom feed URL (used when MODE == 'custom')
FEED_URL: str = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"

# Output control
MAX_ITEMS: int = 15
PRINT_DESCRIPTION: bool = False
SAVE_JSON: bool = False
OUTPUT_JSON: str = "google_news_items.json"

# Networking
REQUEST_TIMEOUT: int = 15
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
EXTRA_HEADERS: Dict[str, str] = {
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


# -----------------------------
# Helpers
# -----------------------------

def _localname(tag: str) -> str:
    """Return the local XML tag name without namespace."""
    return tag.split('}', 1)[-1] if '}' in tag else tag


def build_search_url(query: str, hl: str, gl: str, ceid: str) -> str:
    base = "https://news.google.com/rss/search"
    params = {"q": query, "hl": hl, "gl": gl, "ceid": ceid}
    return f"{base}?{urllib.parse.urlencode(params)}"


def build_topic_url(topic: str, hl: str, gl: str, ceid: str) -> str:
    """Build a Google News RSS URL for a specific topic.

    Topic is usually one of Google’s built-in categories (e.g., TECHNOLOGY),
    and is part of the path rather than a query parameter.
    """
    # Normalize topic to Google’s conventional format (uppercase, underscores)
    normalized = topic.strip().upper().replace(" ", "_")
    base = f"https://news.google.com/rss/headlines/section/topic/{urllib.parse.quote(normalized)}"
    params = {"hl": hl, "gl": gl, "ceid": ceid}
    return f"{base}?{urllib.parse.urlencode(params)}"


def fetch_text(url: str, user_agent: str, headers: Optional[Dict[str, str]] = None, timeout: int = 15) -> str:
    req_headers = {"User-Agent": user_agent}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def parse_rss(xml_text: str) -> Dict[str, object]:
    """
    Parse RSS XML into a dictionary with channel metadata and items.
    Returns a dict: {"title": str, "link": str, "items": List[dict]}.
    """
    root = ET.fromstring(xml_text)

    # Handle <rss><channel>...
    channel = root.find("channel")
    if channel is None:
        # Some feeds might use namespaces; fallback to search
        for child in root.iter():
            if _localname(child.tag) == "channel":
                channel = child
                break
    if channel is None:
        raise ValueError("Invalid RSS: no channel element found")

    feed_title = (channel.findtext("title") or "").strip()
    feed_link = (channel.findtext("link") or "").strip()

    items: List[Dict[str, Optional[str]]] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()

        # Try to extract <source> text (may be namespaced in some feeds)
        source_text = None
        for child in list(item):
            if _localname(child.tag).lower() == "source":
                source_text = (child.text or "").strip()
                break

        items.append(
            {
                "title": title,
                "link": link,
                "source": source_text,
                "pubDate": pub_date,
                "description": description,
            }
        )

    return {"title": feed_title, "link": feed_link, "items": items}


def print_items(feed: Dict[str, object], max_items: int = 10, show_description: bool = False) -> None:
    title = feed.get("title") or "Google News"
    print(f"\nFeed: {title}")
    print("-" * (6 + len(str(title))))

    items: List[Dict[str, Optional[str]]] = feed.get("items", [])  # type: ignore[assignment]
    for i, it in enumerate(items[:max_items], start=1):
        t = it.get("title") or "(no title)"
        link = it.get("link") or ""
        source = it.get("source") or ""
        pub_date = it.get("pubDate") or ""
        print(f"{i:02d}. {t}")
        if source:
            print(f"     Source: {source}")
        if pub_date:
            print(f"     Date:   {pub_date}")
        print(f"     Link:   {link}")
        if show_description and it.get("description"):
            print(f"     Desc:   {it['description']}")
        print()


def save_items_json(feed: Dict[str, object], path: str) -> None:
    out = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "title": feed.get("title"),
        "link": feed.get("link"),
        "items": feed.get("items", []),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(out['items'])} items to {path}")


def resolve_feed_url() -> str:
    mode = MODE.lower().strip()
    if mode == "search":
        return build_search_url(SEARCH_QUERY, HL, GL, CEID)
    if mode == "topic":
        return build_topic_url(TOPIC, HL, GL, CEID)
    if mode == "custom":
        return FEED_URL
    raise ValueError("MODE must be one of: 'search', 'topic', 'custom'")


def main(argv: Optional[List[str]] = None) -> int:
    try:
        url = resolve_feed_url()
        print(f"Fetching: {url}")
        xml_text = fetch_text(url, USER_AGENT, EXTRA_HEADERS, REQUEST_TIMEOUT)
        feed = parse_rss(xml_text)
        print_items(feed, max_items=MAX_ITEMS, show_description=PRINT_DESCRIPTION)
        if SAVE_JSON:
            save_items_json(feed, OUTPUT_JSON)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
