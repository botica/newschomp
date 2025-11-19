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
MAX_ARTICLES = 1

VALID_ATTRIBUTES = {"class", "id", "src", "href", "alt", "title", "value", "type", "name", "width", "height", "role"}
UNWANTED_TAGS = ['script', 'style', 'meta', 'link', 'iframe', 'noscript', 'path', 'svg']
ROOT_TAGS = ('html', 'head', 'body')


class Article:
    def __init__(self, title, link, source, pub_date, description):
        self.title = title
        self.link = link
        self.source = source
        self.pub_date = pub_date
        self.description = description
        self.raw_html = None
        self.html_content = None
        self.summary = None


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
    articles = [
        Article(
            title=(item.find("title").text if item.find("title") else "").strip(),
            link=(item.find("link").text if item.find("link") else "").strip(),
            source=(item.find("source").text if item.find("source") else "").strip() or None,
            pub_date=(item.find("pubDate").text if item.find("pubDate") else "").strip(),
            description=(item.find("description").text if item.find("description") else "").strip() or None,
        )
        for item in channel.find_all("item")
    ]
    return articles


def fetch_articles(articles):
    """Fetch HTML content for articles using Playwright."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        for article in articles:
            url = article.link
            if not url:
                continue
            try:
                page.goto(url, wait_until="load", timeout=TIMEOUT_SECONDS * 1000)
                page.wait_for_timeout(TIMEOUT_SECONDS * 100)
                html = page.content()
                article.raw_html = html
            except Exception as e:
                print(f"no fetch: {e}", file=sys.stderr)
                article.raw_html = None
        browser.close()


def main():
    query = sys.argv[1]
    url = build_search_url(query)
    print(f"fetching: {url}")
    xml_text = fetch_rss(url)
    print('parsing google news feed xml now')
    articles = parse_rss(xml_text)
    articles = articles[:MAX_ARTICLES]
    print('using playwright to gather html')
    fetch_articles(articles)
    for article in articles:
        if article.raw_html:
            print('cleanin html')
            cleaned_html = clean_html(article.raw_html)
            print('html cleaned up nice and good')
            article.html_content = cleaned_html
            print(f'summarizin w {GPT_MODEL}')
            summary = summarize_html(cleaned_html)
            print('summarized')
            article.summary = summary
        title = article.title or '(no title)'
        source = article.source
        pub_date = article.pub_date
        summary = article.summary
        print(f"title: {title}")
        if source:
            print(f"source: {source}")
        if pub_date:
            print(f"date: {pub_date}")
        if summary:
            print(f"summary:\n{summary}")
    return 0

if __name__ == "__main__":
    main()
