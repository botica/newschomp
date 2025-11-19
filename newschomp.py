import os
import re
import sys
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup, Comment
from playwright.sync_api import sync_playwright
from openai import OpenAI

TIMEOUT_SECONDS = 30
GPT_MODEL = "gpt-5.1"

VALID_ATTRIBUTES = {"class", "id", "src", "href", "alt", "title", "value", "type", "name", "width", "height", "role"}
UNWANTED_TAGS = ['script', 'style', 'meta', 'link', 'iframe', 'noscript', 'path', 'svg']
ROOT_TAGS = ('html', 'head', 'body')


def clean_html(html_content):
    """Clean and sanitize HTML content."""
    soup = BeautifulSoup(html_content, 'html.parser')
    for tag in soup.find_all(UNWANTED_TAGS):
        tag.decompose()
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
    for tag in soup.find_all(style=True):
        del tag['style']
    for tag in soup.find_all(onclick=True):
        del tag['onclick']
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    for tag in soup.find_all():
        if tag.name not in ROOT_TAGS and not tag.get_text(strip=True):
            tag.decompose()
    html = str(soup)
    html = re.sub(r'[\r\n]+', ' ', html)
    html = re.sub(r'\s{2,}', ' ', html)
    return html.strip()


def summarize_html(html_content):
    """Summarize HTML content using OpenAI API."""
    try:
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        response = client.responses.create(
            model=GPT_MODEL,
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
        print(f"failed to summarize: {e}", file=sys.stderr)
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
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def parse_rss(xml_text):
    """Parse RSS XML and extract feed items."""
    soup = BeautifulSoup(xml_text, 'xml')
    channel = soup.find("channel")
    if not channel:
        raise ValueError("invalid RSS: no channel element found")
    feed_title = (channel.find("title").text if channel.find("title") else "").strip()
    items = [
        {
            "title": (item.find("title").text if item.find("title") else "").strip(),
            "link": (item.find("link").text if item.find("link") else "").strip(),
            "source": (item.find("source").text if item.find("source") else "").strip() or None,
            "pubDate": (item.find("pubDate").text if item.find("pubDate") else "").strip(),
            "description": (item.find("description").text if item.find("description") else "").strip() or None,
        }
        for item in channel.find_all("item")
    ]
    return feed_title, items


def fetch_article(page, item):
    """Fetch and process a single article."""
    url = item.get("link")
    print(f"fetching: {item.get('title', 'Untitled')[:60]}...")
    try:
        page.goto(url, wait_until="load", timeout=TIMEOUT_SECONDS * 1000)
        page.wait_for_timeout(TIMEOUT_SECONDS * 100)
        print('done waitin fer page')
        html = page.content()
        cleaned_html = clean_html(html)
        print('html cleaned up nice and good')
        item["html_content"] = cleaned_html
        print(f'summarizin w {GPT_MODEL}')
        summary = summarize_html(cleaned_html)
        print('summarized')
        item["summary"] = summary
    except Exception as e:
        print(f"no fetch: {e}", file=sys.stderr)
        item["html_content"] = None


def fetch_articles(items):
    """Fetch HTML content for articles using Playwright."""
    print(f"hi playwright to get {len(items)} articles...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        for item in items:
            fetch_article(page, item)
        browser.close()


def print_items(feed_title, items):
    for i, item in enumerate(items, start=1):
        title = item.get('title') or '(no title)'
        source = item.get('source')
        pub_date = item.get('pubDate')
        summary = item.get('summary')
        print(f"title: {title}")
        print(f"source: {source}")
        print(f"date: {pub_date}")
        print(f"summary:\n{summary}")


def main(argv=None):
    """Main entry point."""
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) < 1:
        print("$newschomp.py <search_query>", file=sys.stderr)
        return 1
    query = argv[0]
    try:
        url = build_search_url(query)
        print(f"fetching: {url}")
        xml_text = fetch_rss(url)
        feed_title, items = parse_rss(xml_text)
        items = items[:1]
        if items:
            fetch_articles(items)
        print_items(feed_title, items)
        return 0
    except Exception as e:
        print(f"err: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    main()
