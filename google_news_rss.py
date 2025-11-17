"""
Google News RSS Fetcher

Fetches Google News RSS feeds, downloads article HTML via Playwright.

Dependencies: beautifulsoup4, playwright
Install: pip install beautifulsoup4 playwright && playwright install
"""
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[assignment,misc]

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None  # type: ignore[assignment,misc]

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
SEARCH_QUERY: str = "Milwaukee restaurant"  # Example query; URL-encoded automatically

# Topic configuration (used when MODE == 'topic')
# Examples (case-insensitive): 'WORLD', 'NATION', 'BUSINESS', 'TECHNOLOGY',
# 'ENTERTAINMENT', 'SCIENCE', 'SPORTS', 'HEALTH'
TOPIC: str = "TECHNOLOGY"

# Custom feed URL (used when MODE == 'custom')
FEED_URL: str = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"

# Output control
MAX_ITEMS: int = 5
SAVE_JSON: bool = True
OUTPUT_JSON: str = "google_news_items.json"
FETCH_HTML_CONTENT: bool = True  # Fetch full HTML of each article page

# Networking
REQUEST_TIMEOUT: int = 15
USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
EXTRA_HEADERS: Dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def main(argv: Optional[List[str]] = None) -> int:
    try:
        # Build RSS feed URL
        mode = MODE.lower().strip()
        if mode == "search":
            base = "https://news.google.com/rss/search"
            params = {"q": SEARCH_QUERY, "hl": HL, "gl": GL, "ceid": CEID, "num": MAX_ITEMS}
            url = f"{base}?{urllib.parse.urlencode(params)}"
        elif mode == "topic":
            normalized = TOPIC.strip().upper().replace(" ", "_")
            base = f"https://news.google.com/rss/headlines/section/topic/{urllib.parse.quote(normalized)}"
            params = {"hl": HL, "gl": GL, "ceid": CEID, "num": MAX_ITEMS}
            url = f"{base}?{urllib.parse.urlencode(params)}"
        elif mode == "custom":
            url = FEED_URL
        else:
            raise ValueError("MODE must be one of: 'search', 'topic', 'custom'")
        
        # Fetch RSS feed
        print(f"Fetching: {url}")
        req_headers = {"User-Agent": USER_AGENT}
        if EXTRA_HEADERS:
            req_headers.update(EXTRA_HEADERS)
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            xml_text = resp.read().decode(charset, errors="replace")
        
        # Parse RSS
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            raise ValueError("Invalid RSS: no channel element found")

        feed_title = (channel.findtext("title") or "").strip()
        feed_link = (channel.findtext("link") or "").strip()
        items: List[Dict[str, Optional[str]]] = []
        for item in channel.findall("item"):
            items.append({
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "source": (item.findtext("source") or "").strip() or None,
                "pubDate": (item.findtext("pubDate") or "").strip(),
            })
        
        # Fetch HTML content for each article if enabled
        if FETCH_HTML_CONTENT:
            if sync_playwright is None:
                print("Warning: Playwright not installed. Run: pip install playwright && playwright install", file=sys.stderr)
            else:
                limited_items = items[:MAX_ITEMS]
                print(f"\nFetching HTML content for {len(limited_items)} articles...")
                
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=USER_AGENT,
                        extra_http_headers={k: v for k, v in EXTRA_HEADERS.items()}
                    )
                    page = context.new_page()
                    
                    for i, item in enumerate(limited_items, start=1):
                        article_url = item.get("link")
                        if article_url:
                            print(f"  [{i}/{len(limited_items)}] {item.get('title', 'Untitled')[:60]}...")
                            try:
                                page.goto(article_url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000)
                                page.wait_for_timeout(2000)  # Wait 2s for dynamic content
                                html_content = page.content()
                                
                                # Parse with BeautifulSoup if available
                                if BeautifulSoup:
                                    soup = BeautifulSoup(html_content, 'html.parser')
                                    item["html_content"] = soup.prettify()
                                else:
                                    item["html_content"] = html_content
                            except Exception as e:
                                print(f"Warning: Failed to fetch {article_url}: {e}", file=sys.stderr)
                                item["html_content"] = None
                    
                    browser.close()
                print()
        
        # Print results
        print(f"\nFeed: {feed_title}")
        print("-" * (6 + len(str(feed_title))))
        for i, it in enumerate(items[:MAX_ITEMS], start=1):
            print(f"{i:02d}. {it.get('title') or '(no title)'}")
            if it.get("source"):
                print(f"     Source: {it['source']}")
            if it.get("pubDate"):
                print(f"     Date:   {it['pubDate']}")
            print(f"     Link:   {it.get('link') or ''}")
            print()
        
        # Save to JSON
        if SAVE_JSON:
            out = {
                "fetched_at": datetime.utcnow().isoformat() + "Z",
                "title": feed_title,
                "link": feed_link,
                "items": items[:MAX_ITEMS],
            }
            with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            print(f"Saved {len(out['items'])} items to {OUTPUT_JSON}")
        
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
