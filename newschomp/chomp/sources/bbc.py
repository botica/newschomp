import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from playwright.sync_api import sync_playwright
from .base import NewsSource


class BBCSource(NewsSource):
    """BBC News article source implementation"""

    @property
    def name(self):
        return "BBC News"

    @property
    def source_key(self):
        return "bbc"

    def fetch(self, url):
        """
        Fetch HTML content from BBC using Playwright headless browser.

        Args:
            url: URL to fetch

        Returns:
            str: HTML content as string
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Navigate to the URL and wait for DOM to be ready
            page.goto(url, wait_until='domcontentloaded', timeout=15000)

            # Wait a bit for dynamic content to load
            page.wait_for_timeout(2000)

            # Get the HTML content
            html = page.content()

            browser.close()

        return html

    def search(self, query=None):
        """
        Fetch BBC World News articles from the world news page.

        Args:
            query: Ignored, fetches from fixed world news URL

        Returns:
            list: List of article URLs sorted by recency, or empty list if not found
        """
        # Fetch world news page
        world_news_url = "https://www.bbc.com/news/world"

        print(f"Fetching BBC World News: {world_news_url}")

        # Fetch world news page with headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        response = requests.get(world_news_url, headers=headers)
        response.raise_for_status()

        # Parse page
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all article divs with class "sc-225578b-0 ezQaGx"
        article_divs = soup.find_all('div', class_='sc-225578b-0 ezQaGx')
        if not article_divs:
            print("No articles found")
            return []

        # Collect all valid article URLs
        article_urls = []
        for article_div in article_divs:
            # Find the link with class "sc-8a623a54-0 huZCWi"
            link_element = article_div.find('a', class_='sc-8a623a54-0 huZCWi')
            if not link_element:
                continue

            article_url = link_element.get('href')
            if not article_url:
                continue

            # Handle relative URLs
            if not article_url.startswith('http'):
                article_url = f"https://www.bbc.com{article_url}"

            # Check if it's an article URL
            # BBC articles follow the pattern: /{category}/article(s)/{article-id}
            # Examples: /news/articles/..., /travel/article/..., /culture/articles/...
            # Note: Some sections use singular /article/ while others use plural /articles/
            is_article = '/article/' in article_url or '/articles/' in article_url

            # Also verify it's a BBC domain (bbc.com or bbc.co.uk)
            is_bbc_domain = 'bbc.com' in article_url or 'bbc.co.uk' in article_url

            # Skip sport articles - we're using BBC for world news, not sports
            # Sport articles also have different HTML structure that breaks content extraction
            is_sport = '/sport/articles/' in article_url

            if is_article and is_bbc_domain and not is_sport:
                print(f"Found article URL: {article_url}")
                article_urls.append(article_url)
            else:
                print(f"Skipping non-article URL: {article_url}")

        if not article_urls:
            print("No article URLs found")
        else:
            print(f"Found {len(article_urls)} article URLs")

        return article_urls

    def extract(self, html_string):
        """
        Extract BBC News article data from HTML string.

        Args:
            html_string: HTML content as string

        Returns:
            dict: Dictionary containing title, url, pub_date, content
        """
        soup = BeautifulSoup(html_string, 'html.parser')

        # Extract meta tags
        title_tag = soup.find('meta', property='og:title')

        # BBC doesn't use og:url, try canonical link instead
        url_tag = soup.find('link', rel='canonical')
        if url_tag:
            url = url_tag.get('href')
        else:
            # Try og:url as fallback
            og_url_tag = soup.find('meta', property='og:url')
            url = og_url_tag.get('content') if og_url_tag else None

        pub_date_tag = soup.find('meta', property='article:published_time')

        print(f"DEBUG: title_tag = {title_tag}")
        print(f"DEBUG: url from canonical = {url}")
        print(f"DEBUG: pub_date_tag = {pub_date_tag}")

        # Extract content from <p class="sc-9a00e533-0 eZyhnA"> tags
        content_paragraphs = soup.find_all('p', class_='sc-9a00e533-0 eZyhnA')
        print(f"DEBUG: Found {len(content_paragraphs)} content paragraphs with class 'sc-9a00e533-0 eZyhnA'")

        # If that class doesn't work, try finding all <p> tags to see what's there
        if not content_paragraphs:
            all_p_tags = soup.find_all('p', limit=5)
            print(f"DEBUG: First 5 <p> tags found:")
            for i, p in enumerate(all_p_tags):
                print(f"  {i+1}. class={p.get('class')} | text={p.get_text(strip=True)[:100]}")

        # Extract text from paragraphs, handling <a> tags
        content_text = []
        for para in content_paragraphs:
            # Get text with all nested tags (including <a> tags)
            para_text = para.get_text(separator=' ', strip=True)
            if para_text:
                content_text.append(para_text)

        # Join all paragraphs with newlines
        content = '\n'.join(content_text) if content_text else None
        print(f"DEBUG: Final content length: {len(content) if content else 0}")

        # Extract image URL
        # Priority: VideoObject thumbnail (for video articles) > figure images > direct images
        import json
        image_url = None

        # First, check for VideoObject JSON-LD schema (video articles should use video thumbnail)
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if data.get('@type') == 'VideoObject' and data.get('thumbnailUrl'):
                    thumb_url = data['thumbnailUrl']
                    # Replace $recipe placeholder with large dimensions (BBC CDN resizes)
                    if '$recipe' in thumb_url:
                        thumb_url = thumb_url.replace('$recipe', '1920x1080')
                    image_url = thumb_url
                    print(f"DEBUG: Found VideoObject thumbnailUrl: {image_url}")
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        # Try holding_image with srcset (video player poster)
        if not image_url:
            img_tag = soup.find('img', class_='holding_image')
            if img_tag:
                srcset = img_tag.get('srcset', '')
                if srcset and 'ichef.bbci.co.uk' in srcset:
                    parts = srcset.split(',')
                    for part in reversed(parts):
                        url = part.strip().split()[0]
                        if 'ichef.bbci.co.uk' in url:
                            image_url = url
                            print(f"DEBUG: Found holding_image srcset URL: {image_url}")
                            break
                if not image_url:
                    image_url = img_tag.get('src')
                    if image_url:
                        print(f"DEBUG: Found holding_image URL: {image_url}")

        # Try figure tag images
        if not image_url:
            figure = soup.find('figure')
            if figure:
                img_tag = figure.find('img', class_='sc-5340b511-0 hLdNfA')
                if img_tag:
                    image_url = img_tag.get('src')
                    print(f"DEBUG: Found image URL in figure: {image_url}")
                else:
                    img_tag = figure.find('img')
                    if img_tag:
                        image_url = img_tag.get('src')
                        print(f"DEBUG: Found fallback image URL in figure: {image_url}")

        # Try direct images on page
        if not image_url:
            img_tag = soup.find('img', class_='sc-5340b511-0 hLdNfA')
            if img_tag:
                src = img_tag.get('src', '')
                if 'ichef.bbci.co.uk' in src:
                    image_url = src
                    print(f"DEBUG: Found image URL directly: {image_url}")

        if not image_url:
            print("DEBUG: No image URL found")

        # Parse publication date
        pub_date = None
        if pub_date_tag:
            pub_date_str = pub_date_tag.get('content')
            if pub_date_str:
                try:
                    # Parse ISO format datetime
                    pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                    # Convert to Django timezone-aware datetime
                    if timezone.is_naive(pub_date):
                        pub_date = timezone.make_aware(pub_date)
                except (ValueError, AttributeError):
                    pub_date = timezone.now()

        # Extract topics using LLM
        topics = []
        if content:
            from ..utils import extract_topics_with_llm
            topics = extract_topics_with_llm(content)

        # Build result dictionary
        result = {
            'title': title_tag.get('content') if title_tag else None,
            'url': url,
            'pub_date': pub_date,
            'content': content,
            'image_url': image_url,
            'topics': topics
        }

        print(f"DEBUG: Result - title={result['title']}, url={result['url']}, content_exists={bool(result['content'])}")

        return result
