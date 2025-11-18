import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
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


# Constants
VALID_ATTRIBUTES = {"class", "id", "src", "href", "alt", "title", "value", "type", "name", "width", "height", "role"}
UNWANTED_TAGS = ['script', 'style', 'meta', 'link', 'iframe', 'noscript', 'path', 'svg']
ROOT_TAGS = ('html', 'head', 'body')


@dataclass
class Config:
    """Configuration for Google News RSS fetcher."""
    search_query: str
    
    # Localization
    hl: str = "en-US"
    gl: str = "US"
    ceid: str = "US:en"
    
    # Processing options
    max_items: int = 1
    
    # Network settings
    timeout: int = 30
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    @property
    def headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }


class HTMLCleaner:
    """Clean and sanitize HTML content."""
    
    @staticmethod
    def clean_attribute_value(value: str) -> str:
        """Remove escaped quotes from attribute value."""
        return re.sub(r'^\\?"|\\?"$', '', value).replace('\\"', '').strip()
    
    @staticmethod
    def remove_unwanted_tags(soup: BeautifulSoup) -> None:
        """Remove script, style, and other unwanted tags."""
        for tag in soup.find_all(UNWANTED_TAGS):
            tag.decompose()
    
    @staticmethod
    def sanitize_attributes(soup: BeautifulSoup) -> None:
        """Remove invalid attributes and clean valid ones."""
        for tag in soup.find_all(True):
            for attr in list(tag.attrs.keys()):
                if attr not in VALID_ATTRIBUTES:
                    del tag.attrs[attr]
                else:
                    value = tag[attr]
                    if isinstance(value, list):
                        tag[attr] = [HTMLCleaner.clean_attribute_value(v) for v in value if isinstance(v, str)]
                    elif isinstance(value, str):
                        tag[attr] = HTMLCleaner.clean_attribute_value(value)
    
    @staticmethod
    def remove_event_handlers(soup: BeautifulSoup) -> None:
        """Remove inline styles and JavaScript event handlers."""
        for tag in soup.find_all(style=True):
            del tag['style']
        for tag in soup.find_all(onclick=True):
            del tag['onclick']
    
    @staticmethod
    def remove_comments(soup: BeautifulSoup) -> None:
        """Remove HTML comments."""
        if Comment:
            for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                comment.extract()
    
    @staticmethod
    def remove_empty_tags(soup: BeautifulSoup) -> None:
        """Remove empty tags except root elements."""
        for tag in soup.find_all():
            if tag.name not in ROOT_TAGS and not tag.get_text(strip=True):
                tag.decompose()
    
    @staticmethod
    def normalize_whitespace(html: str) -> str:
        """Normalize whitespace in HTML string."""
        html = re.sub(r'[\r\n]+', ' ', html)
        html = re.sub(r'\s{2,}', ' ', html)
        return html.strip()
    
    @classmethod
    def clean(cls, html_content: str) -> str:
        """Clean and sanitize HTML content."""
        if not BeautifulSoup:
            return html_content
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        cls.remove_unwanted_tags(soup)
        cls.sanitize_attributes(soup)
        cls.remove_event_handlers(soup)
        cls.remove_comments(soup)
        cls.remove_empty_tags(soup)
        
        return cls.normalize_whitespace(str(soup))


class ArticleSummarizer:
    """Summarize article content using OpenAI."""
    
    SUMMARIZATION_PROMPT = """
    this is somewhat cleaned html of a news article. 
    condense the content of the article into 3 lines. 
    also provide a short title (think 3 words). 
    ignore ads and unrelated stories/info. 
    speak objectively, and dont provide a meta perspective, but present the news as an original source.  
    """
    
    @staticmethod
    def summarize(html_content: str) -> Optional[str]:
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
                instructions=ArticleSummarizer.SUMMARIZATION_PROMPT,
                input=html_content,
            )
            return response.output_text
        except Exception as e:
            print(f"    Warning: Failed to summarize: {e}", file=sys.stderr)
            return None


def build_search_url(config: Config) -> str:
    """Build search feed URL."""
    params = {
        "q": config.search_query,
        "hl": config.hl,
        "gl": config.gl,
        "ceid": config.ceid,
        "num": config.max_items
    }
    return f"https://news.google.com/rss/search?{urllib.parse.urlencode(params)}"


class RSSParser:
    """Parse RSS feed XML."""
    
    @staticmethod
    def parse(xml_text: str) -> tuple[str, str, List[Dict[str, Optional[str]]]]:
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
                "description": (item.findtext("description") or "").strip() or None,
            }
            for item in channel.findall("item")
        ]
        
        return feed_title, feed_link, items


class ArticleFetcher:
    """Fetch article HTML content using Playwright."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def fetch_articles(self, items: List[Dict[str, Optional[str]]]) -> None:
        """Fetch HTML content for articles using Playwright."""
        if not sync_playwright:
            print("Warning: Playwright not installed. Run: pip install playwright && playwright install", file=sys.stderr)
            return
        
        print(f"Using playwright to get {len(items)} articles...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=self.config.user_agent)
            
            for i, item in enumerate(items, start=1):
                self._fetch_single_article(page, item, i, len(items))
            
            browser.close()
        #print()
    
    def _fetch_single_article(self, page, item: Dict, index: int, total: int) -> None:
        """Fetch and process a single article."""
        url = item.get("link")
        if not url:
            return
        
        print(f"  [{index}/{total}] {item.get('title', 'Untitled')[:60]}...")
        
        try:
            page.goto(url, wait_until="load", timeout=self.config.timeout * 1000)
            page.wait_for_timeout(3000)
            html = page.content()
            
            # Clean HTML
            cleaned_html = HTMLCleaner.clean(html)
            item["html_content"] = cleaned_html
            
            # Summarize
            summary = ArticleSummarizer.summarize(cleaned_html)
            if summary:
                item["summary"] = summary
        except Exception as e:
            print(f"    Warning: Failed to fetch: {e}", file=sys.stderr)
            item["html_content"] = None


class OutputManager:
    """Handle output formatting."""
    
    @staticmethod
    def print_items(feed_title: str, items: List[Dict[str, Optional[str]]]) -> None:
        """Print feed items to console."""
        print(f"\nFeed: {feed_title}\n")
        
        for i, item in enumerate(items, start=1):
            title = item.get('title') or '(no title)'
            source = item.get('source')
            pub_date = item.get('pubDate')
            description = item.get('description')
            link = item.get('link') or ''
            summary = item.get('summary')
            
            print(f"{i:02d}. {title}")
            if source:
                print(f"Source: {source}")
            if pub_date:
                print(f"Date: {pub_date}")
            #if description:
                #print(f"Description: {description}")
            #if link:
                #print(f"Link: {link}")
            if summary:
                print(f"bot summary:\n{summary}")
            #print()


class GoogleNewsRSS:
    """Main orchestrator for Google News RSS fetching."""
    
    def __init__(self, config: Config):
        self.config = config
        self.article_fetcher = ArticleFetcher(config)
    
    def fetch_rss(self, url: str) -> str:
        """Fetch RSS feed XML from URL."""
        req = urllib.request.Request(url, headers=self.config.headers, method="GET")
        with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    
    def run(self) -> int:
        """Execute the RSS fetcher workflow."""
        try:
            # Build and fetch RSS feed
            url = build_search_url(self.config)
            print(f"Fetching: {url}")
            
            xml_text = self.fetch_rss(url)
            feed_title, feed_link, items = RSSParser.parse(xml_text)
            
            # Limit items
            items = items[:self.config.max_items]
            
            # Fetch article HTML
            if items:
                self.article_fetcher.fetch_articles(items)
            
            # Output results
            OutputManager.print_items(feed_title, items)
            
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fetch and summarize Google News articles")
    parser.add_argument('query', help="Search query")
    args = parser.parse_args(argv)
    
    config = Config(search_query=args.query)
    fetcher = GoogleNewsRSS(config)
    return fetcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
