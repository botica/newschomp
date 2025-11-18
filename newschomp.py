"""Google News RSS Fetcher - Fetch RSS feeds and article HTML via Playwright."""

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

try:
    from bs4 import BeautifulSoup, Comment
except ImportError:
    BeautifulSoup = None
    Comment = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


@dataclass
class Config:
    """Configuration for Google News RSS fetcher."""
    mode: str = "search"  # 'search', 'topic', or 'custom'
    search_query: str = "Milwaukee restaurant"
    topic: str = "TECHNOLOGY"
    custom_url: str = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
    
    hl: str = "en-US"
    gl: str = "US"
    ceid: str = "US:en"
    
    max_items: int = 1
    save_json: bool = True
    output_file: str = "google_news_items.json"
    fetch_html: bool = True
    summarize: bool = True
    
    timeout: int = 15
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    @property
    def headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }


class GoogleNewsRSS:
    """Fetch and parse Google News RSS feeds with optional HTML content."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def strip_html(self, html_content: str) -> str:
        """Remove unwanted tags, invalid attributes, empty tags, and comments."""
        if not BeautifulSoup:
            return html_content
        
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove script-like tags
        for tag in soup.find_all(['script', 'style', 'meta', 'link', 'iframe', 'noscript', 'path', 'svg']):
            tag.decompose()

        # VALID / SAFE HTML ATTRIBUTES
        VALID_ATTRIBUTES = {
            "class", "id", "src", "href", "alt", "title", "value",
            "type", "name", "width", "height", "role"
        }

        # Strip invalid or broken attributes
        for tag in soup.find_all(True):
            for attr in list(tag.attrs.keys()):
                if attr not in VALID_ATTRIBUTES:
                    del tag.attrs[attr]
                else:
                    value = tag[attr]

                    # Clean lists or strings
                    if isinstance(value, list):
                        cleaned_values = [
                            # Remove leading/trailing escaped quotes (e.g., \"value\" -> value)
                            re.sub(r'^\\?"|\\?"$', '', v).replace('\\"', '').strip()
                            for v in value if isinstance(v, str)
                        ]
                        tag[attr] = cleaned_values
                    elif isinstance(value, str):
                        # Remove leading/trailing escaped quotes and unescape inner quotes
                        tag[attr] = re.sub(r'^\\?"|\\?"$', '', value).replace('\\"', '').strip()

        # Remove inline styles and JS event handlers
        for tag in soup.find_all(style=True):
            del tag['style']
        for tag in soup.find_all(onclick=True):
            del tag['onclick']

        # Remove HTML comments
        if Comment:
            for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()

        # Remove empty tags except root
        for tag in soup.find_all():
            if tag.name not in ('html', 'head', 'body') and not tag.get_text(strip=True):
                tag.decompose()

        # Clean whitespace
        html_str = str(soup)
        # Replace all newlines and carriage returns with single space
        html_str = re.sub(r'[\r\n]+', ' ', html_str)
        # Replace multiple consecutive spaces with single space
        html_str = re.sub(r'\s{2,}', ' ', html_str)

        return html_str.strip()
    
    def summarize_html(self, html_content: str) -> Optional[str]:
        """Summarize HTML content using OpenAI API."""
        if not OpenAI:
            print("Warning: OpenAI not installed. Run: pip install openai", file=sys.stderr)
            return None
        
        if not html_content:
            return None
        
        try:
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            
            response = client.responses.create(
                model="gpt-5.1",
                instructions="""
                this is somewhat cleaned html of a news article. 
                condense the content of the article into 3 lines. 
                also provide a short title (think 3 words). 
                ignore ads and unrelated stories/info. 
                speak objectively, and dont provide a meta perspective, but offer the news as an original source.  
                """,
                input=html_content,
            )
            
            return response.output_text
        except Exception as e:
            print(f"    Warning: Failed to summarize: {e}", file=sys.stderr)
            return None
    
    def build_feed_url(self) -> str:
        """Build RSS feed URL based on configuration mode."""
        mode = self.config.mode.lower().strip()
        params = {"hl": self.config.hl, "gl": self.config.gl, "ceid": self.config.ceid}
        
        if mode == "search":
            base = "https://news.google.com/rss/search"
            params["q"] = self.config.search_query
            params["num"] = self.config.max_items
        elif mode == "topic":
            topic = self.config.topic.strip().upper().replace(" ", "_")
            base = f"https://news.google.com/rss/headlines/section/topic/{urllib.parse.quote(topic)}"
            params["num"] = self.config.max_items
        elif mode == "custom":
            return self.config.custom_url
        else:
            raise ValueError("mode must be 'search', 'topic', or 'custom'")
        
        return f"{base}?{urllib.parse.urlencode(params)}"
    
    def fetch_rss(self, url: str) -> str:
        """Fetch RSS feed XML from URL."""
        req = urllib.request.Request(url, headers=self.config.headers, method="GET")
        with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    
    def parse_rss(self, xml_text: str) -> tuple[str, str, List[Dict[str, Optional[str]]]]:
        """Parse RSS XML and extract feed metadata and items."""
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            raise ValueError("Invalid RSS: no channel element found")
        
        feed_title = (channel.findtext("title") or "").strip()
        feed_link = (channel.findtext("link") or "").strip()
        
        items = [
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "source": (item.findtext("source") or "").strip() or None,
                "pubDate": (item.findtext("pubDate") or "").strip(),
            }
            for item in channel.findall("item")
        ]
        
        return feed_title, feed_link, items
    
    def fetch_article_html(self, items: List[Dict[str, Optional[str]]]) -> None:
        """Fetch HTML content for articles using Playwright."""
        if not sync_playwright:
            print("Warning: Playwright not installed. Run: pip install playwright && playwright install", file=sys.stderr)
            return
        
        print(f"\nFetching HTML content for {len(items)} articles...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=self.config.user_agent)
            
            for i, item in enumerate(items, start=1):
                url = item.get("link")
                if not url:
                    continue
                
                print(f"  [{i}/{len(items)}] {item.get('title', 'Untitled')[:60]}...")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=self.config.timeout * 1000)
                    page.wait_for_timeout(2000)
                    html = page.content()
                    
                    # Strip and clean the HTML
                    cleaned_html = self.strip_html(html)
                    item["html_content"] = cleaned_html
                    
                    # Summarize the HTML content if enabled
                    if self.config.summarize:
                        summary = self.summarize_html(cleaned_html)
                        if summary:
                            item["summary"] = summary
                except Exception as e:
                    print(f"    Warning: Failed to fetch: {e}", file=sys.stderr)
                    item["html_content"] = None
            
            browser.close()
        print()
    
    def print_items(self, feed_title: str, items: List[Dict[str, Optional[str]]]) -> None:
        """Print feed items to console."""
        print(f"\nFeed: {feed_title}")
        print("-" * (6 + len(feed_title)))
        
        for i, item in enumerate(items, start=1):
            print(f"{i:02d}. {item.get('title') or '(no title)'}")
            if item.get("source"):
                print(f"     Source: {item['source']}")
            if item.get("pubDate"):
                print(f"     Date:   {item['pubDate']}")
            print(f"     Link:   {item.get('link') or ''}")
            if item.get("summary"):
                print(f"     Summary:\n     {item['summary']}")
            print()
    
    def save_json(self, feed_title: str, feed_link: str, items: List[Dict[str, Optional[str]]]) -> None:
        """Save feed data to JSON file."""
        output = {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "title": feed_title,
            "link": feed_link,
            "items": items,
        }
        
        with open(self.config.output_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"Saved {len(items)} items to {self.config.output_file}")
    
    def run(self) -> int:
        """Execute the RSS fetcher workflow."""
        try:
            url = self.build_feed_url()
            print(f"Fetching: {url}")
            
            xml_text = self.fetch_rss(url)
            feed_title, feed_link, items = self.parse_rss(xml_text)
            
            items = items[:self.config.max_items]
            
            if self.config.fetch_html and items:
                self.fetch_article_html(items)
            
            self.print_items(feed_title, items)
            
            if self.config.save_json:
                self.save_json(feed_title, feed_link, items)
            
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fetch Google News RSS feeds with optional HTML content")
    parser.add_argument('query', nargs='?', help="Search query (overrides default)")
    parser.add_argument('-m', '--mode', choices=['search', 'topic', 'custom'], help="Feed mode")
    parser.add_argument('-n', '--max-items', type=int, help="Maximum number of items to fetch")
    parser.add_argument('--no-html', action='store_true', help="Skip fetching HTML content")
    parser.add_argument('--no-summarize', action='store_true', help="Skip summarizing HTML content")
    parser.add_argument('-o', '--output', help="Output JSON file path")
    
    args = parser.parse_args(argv)
    
    config = Config()
    
    # Override config with command line arguments
    if args.query:
        config.search_query = args.query
    if args.mode:
        config.mode = args.mode
    if args.max_items:
        config.max_items = args.max_items
    if args.no_html:
        config.fetch_html = False
    if args.no_summarize:
        config.summarize = False
    if args.output:
        config.output_file = args.output
    
    fetcher = GoogleNewsRSS(config)
    return fetcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
