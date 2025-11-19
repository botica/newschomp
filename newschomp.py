#NewsChomp - condensed news

import os
import re
import sys
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup, Comment
from playwright.sync_api import sync_playwright
from openai import OpenAI

TIMEOUT = 30
GPT = "gpt-5.1"
MAX_ART = 1 # how many articles to fetch html for and summarize

VALID_ATTRIBUTES = {"class", "id", "src", "href", "alt", "title", "value", "type", "name", "width", "height", "role"}
UNWANTED_TAGS = ['script', 'style', 'meta', 'link', 'iframe', 'noscript', 'path', 'svg']
ROOT_TAGS = ('html', 'head', 'body')


class Article:
    def __init__(self, title, pub_date, url):
        self.title = title
        self.url = url
        self.pub_date = pub_date
        self.html_content = None
    
    def gather_html(self, page):
        """fetches and stores html content using playwright browser page"""
        try:
            page.goto(self.url, wait_until="load", timeout=TIMEOUT * 1000)
            page.wait_for_timeout(TIMEOUT * 100)
            self.html_content = page.content()
        except Exception as e:
            print(f"no fetch for {self.url}: {e}", file=sys.stderr)

    def clean_html(self):
        """cleans self.html_content of unwanted tags and atrributes"""
        soup = BeautifulSoup(self.html_content, 'html.parser')
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
        self.html_content = html.strip()

    def summarize(self):
        """return string summary from gpt"""
        try:
            client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            response = client.responses.create(
                model=GPT,
                instructions="""
                this is somewhat cleaned html of a news article. 
                condense the content of the article into 3 lines. 
                also provide a short title (think 3 words). 
                ignore ads and unrelated stories/info. 
                speak objectively, and dont provide a meta perspective, but present the news as an original source.  
                """,
                input=self.html_content,
            )
            return response.output_text
        except Exception as e:
            print(f"failed to summarize: {e}", file=sys.stderr)
            return None


def build_url(query):
    """build google news url with search query from command line arg"""
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en", "num": 1}
    return f"https://news.google.com/rss/search?{urllib.parse.urlencode(params)}"


def fetch_xml(url):
    """download xml from google news with url string"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def build_articles(xml):
    """parse google news xml string and extract/build articles, return list of articles"""
    soup = BeautifulSoup(xml, 'xml')
    channel = soup.find("channel")
    if not channel:
        raise ValueError("invalid RSS: no channel element found")
    articles = [
        Article(
            title=(item.find("title").text if item.find("title") else "").strip(),
            pub_date=(item.find("pubDate").text if item.find("pubDate") else "").strip(),
            url=(item.find("link").text if item.find("link") else "").strip(),
        )
        for item in channel.find_all("item")
    ]
    return articles


def main():
    query = sys.argv[1]
    url = build_url(query)
    print(f"fetching: {url}")
    xml = fetch_xml(url)
    print('parsing google news feed xml now')
    articles = build_articles(xml) # parses xml for rss feed; gathers attributes from rss items and returns a list of Article objects
    articles = articles[:MAX_ART] #truncate list to number of desired Articles
    print('using playwright to gather html')
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        for article in articles:
            article.gather_html(page) # retrieve html for each google news rss item and set to self.html_content
        browser.close() # done with playwright
    for article in articles:
        print('cleanin html')
        article.clean_html() # strips self.html_content
        print(f'summarizin w {GPT}')
        summary = article.summarize() # call to OpenAI model
        print(f"title: {article.title}")
        print(f"source: {article.url}")
        print(f"date: {article.pub_date}")
        print(f"summary:\n{summary}")

if __name__ == "__main__":
    main()
