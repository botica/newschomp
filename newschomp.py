"""Google News RSS Fetcher - Fetch and summarize news articles."""

import argparse
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

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


VALID_ATTRIBUTES = {"class", "id", "src", "href", "alt", "title", "value", "type", "name", "width", "height", "role"}
UNWANTED_TAGS = ['script', 'style', 'meta', 'link', 'iframe', 'noscript', 'path', 'svg']
ROOT_TAGS = ('html', 'head', 'body')


def clean_html(html_content):
    """Clean and sanitize HTML content."""
    if not BeautifulSoup:
        return html_content
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove unwanted tags
    for tag in soup.find_all(UNWANTED_TAGS):
        tag.decompose()
    
    # Remove invalid attributes
    for tag in soup.find_all(True):
        for attr in list(tag.attrs.keys()):
            if attr not in VALID_ATTRIBUTES:
                del tag.attrs[attr]
            else:
                value = tag[attr]
                if isinstance(value, list):
                    tag[attr] = [re.sub(r'^\\?"|\\?"$', '', v).replace('\\"', '').strip() for v in value if isinstance(v, str)]
                elif isinstance(value, str):
                    tag[attr] = re.sub(r'^\\?"|\\?"$', '', value).replace('\\"', '').strip()
    
    # Remove inline styles and event handlers
    for tag in soup.find_all(style=True):
        del tag['style']
    for tag in soup.find_all(onclick=True):
        del tag['onclick']
    
    # Remove comments
    if Comment:
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
    
    # Remove empty tags
    for tag in soup.find_all():
        if tag.name not in ROOT_TAGS and not tag.get_text(strip=True):
            tag.decompose()
    
    # Normalize whitespace
    html = str(soup)
    html = re.sub(r'[\r\n]+', ' ', html)
    html = re.sub(r'\s{2,}', ' ', html)
    return html.strip()


def summarize_html(html_content):
    """Summarize HTML content using OpenAI API."""
    if not OpenAI or not html_content:
        return None
    
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.responses.create(
            model="gpt-5-nano",
            instructions="""
            this is somewhat cleaned html of a news article. 
            condense the content of the article into 3 lines. 
            also provide a short title (think 3 words). 
            ignore ads and unrelated stories/info. 
            speak objectively, and dont provide a meta perspective, but present the news as an original source.  
            """,
            input=html_content,
        )
        return response.output_text
    except Exception as e:
        print(f"Warning: Failed to summarize: {e}", file=sys.stderr)
        return None


def build_search_url(query):
    """Build Google News search URL."""
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en", "num": 1}
    return f"https://news.google.com/rss/search?{urllib.parse.urlencode(params)}"


def fetch_rss(url):
    """Fetch RSS feed XML from URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def parse_rss(xml_text):
    """Parse RSS XML and extract feed items."""
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if not channel:
        raise ValueError("Invalid RSS: no channel element found")
    
    feed_title = (channel.findtext("title") or "").strip()
    
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
    
    return feed_title, items


def fetch_article(page, item):
    """Fetch and process a single article."""
    url = item.get("link")
    if not url:
        return
    
    print(f"  Fetching: {item.get('title', 'Untitled')[:60]}...")
    
    try:
        page.goto(url, wait_until="load", timeout=30000)
        page.wait_for_timeout(3000)
        html = page.content()
        
        cleaned_html = clean_html(html)
        item["html_content"] = cleaned_html
        
        summary = summarize_html(cleaned_html)
        if summary:
            item["summary"] = summary
    except Exception as e:
        print(f"    Warning: Failed to fetch: {e}", file=sys.stderr)
        item["html_content"] = None


def fetch_articles(items):
    """Fetch HTML content for articles using Playwright."""
    if not sync_playwright:
        print("Warning: Playwright not installed", file=sys.stderr)
        return
    
    print(f"Using playwright to get {len(items)} articles...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        for item in items:
            fetch_article(page, item)
        
        browser.close()


def print_items(feed_title, items):
    """Print feed items to console."""
    print(f"\nFeed: {feed_title}\n")
    
    for i, item in enumerate(items, start=1):
        title = item.get('title') or '(no title)'
        source = item.get('source')
        pub_date = item.get('pubDate')
        summary = item.get('summary')
        
        print(f"{i:02d}. {title}")
        if source:
            print(f"Source: {source}")
        if pub_date:
            print(f"Date: {pub_date}")
        if summary:
            print(f"bot summary:\n{summary}")


def main(argv=None):
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fetch and summarize Google News articles")
    parser.add_argument('query', help="Search query")
    args = parser.parse_args(argv)
    
    try:
        url = build_search_url(args.query)
        print(f"Fetching: {url}")
        
        xml_text = fetch_rss(url)
        feed_title, items = parse_rss(xml_text)
        
        items = items[:1]
        
        if items:
            fetch_articles(items)
        
        print_items(feed_title, items)
        
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
