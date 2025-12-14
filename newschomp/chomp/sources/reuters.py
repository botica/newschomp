import random
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class ReutersSource(NewsSource):
    """Reuters World News article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://www.reuters.com/world/',
    ]

    @property
    def name(self):
        return "Reuters"

    @property
    def source_key(self):
        return "reuters"

    def fetch(self, url):
        """
        Fetch HTML content from a URL using Playwright Firefox for JavaScript rendering.

        Args:
            url: URL to fetch

        Returns:
            str: HTML content as string
        """
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.firefox.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/New_York',
                )
                page = context.new_page()
                page.goto(url, wait_until='load', timeout=30000)

                # Wait for article content to load
                try:
                    page.wait_for_selector('.article-body-module__paragraph__Ts-yF', timeout=15000)
                    print('Found article paragraphs!')
                except:
                    print('Article element not found, continuing...')
                    page.wait_for_timeout(5000)

                html = page.content()
                browser.close()
                return html
        except Exception as e:
            print(f"Error fetching article with Playwright: {e}")
            raise

    def search(self, query=None):
        """
        Get article URLs from Reuters World news page using Playwright.
        Article links have class 'text-module__text__0GDob'.

        Args:
            query: Not used for this source (can be None)

        Returns:
            list: List of article URLs from the category
        """
        from playwright.sync_api import sync_playwright

        # Shuffle category pages to randomize which one we try first
        category_pages = self.CATEGORY_PAGES.copy()
        random.shuffle(category_pages)

        for category_url in category_pages:
            print(f"Fetching articles from category: {category_url}")

            try:
                with sync_playwright() as p:
                    # Try Firefox - sometimes works better with bot detection
                    browser = p.firefox.launch(headless=True)
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                        viewport={'width': 1920, 'height': 1080},
                        locale='en-US',
                        timezone_id='America/New_York',
                    )
                    page = context.new_page()

                    page.goto(category_url, wait_until='load', timeout=30000)

                    # Wait for page content to load
                    try:
                        page.wait_for_selector('a[data-testid="TitleLink"]', timeout=20000)
                        print("Found TitleLink selector!")
                    except:
                        print("No article links found via selector, waiting longer...")
                        page.wait_for_timeout(10000)

                    html = page.content()
                    print(f"Page HTML length: {len(html)}")
                    browser.close()

                # Parse the HTML
                soup = BeautifulSoup(html, 'html.parser')

                # Find all article links with data-testid="TitleLink"
                article_urls = []
                article_links = soup.find_all('a', attrs={'data-testid': 'TitleLink'})
                print(f"Found {len(article_links)} article links with data-testid='TitleLink'")

                for link in article_links:
                    href = link.get('href')
                    if href:
                        # Handle relative URLs
                        if href.startswith('/'):
                            href = f"https://www.reuters.com{href}"
                        # Only include reuters.com articles
                        if 'reuters.com' in href:
                            article_urls.append(href)

                # Remove duplicates while preserving order
                # Skip live blog articles which have a different page structure.
                # Using '-live-' to catch slugs like "verdict-live-hong-kong".
                # This may filter out some regular articles with "live" in the title
                # but that's acceptable for world news.
                seen = set()
                unique_urls = []
                for url in article_urls:
                    if url not in seen and '-live-' not in url:
                        seen.add(url)
                        unique_urls.append(url)

                if unique_urls:
                    print(f"Found {len(unique_urls)} unique article URLs")
                    for url in unique_urls[:5]:
                        print(f"  {url}")
                    return unique_urls
                else:
                    print(f"No articles found on {category_url}, trying next category...")

            except Exception as e:
                print(f"Error fetching category page {category_url}: {type(e).__name__}: {e}")
                continue

        print("All category pages failed or returned no articles")
        return []

    def extract(self, html_string):
        """
        Extract Reuters article data from HTML string.

        Args:
            html_string: HTML content as string

        Returns:
            dict: Dictionary containing title, url, pub_date, content, image_url, and topics
        """
        soup = BeautifulSoup(html_string, 'html.parser')

        # Extract title from og:title meta tag
        title_tag = soup.find('meta', property='og:title')
        title = title_tag.get('content') if title_tag else None

        # Extract URL from canonical link or og:url
        url_tag = soup.find('link', rel='canonical')
        if not url_tag:
            url_tag = soup.find('meta', property='og:url')
            url = url_tag.get('content') if url_tag else None
        else:
            url = url_tag.get('href') if url_tag else None

        # Try to extract publication date
        pub_date = None
        pub_date_tag = soup.find('meta', property='article:published_time') or \
                       soup.find('meta', property='og:published_time')

        if pub_date_tag:
            pub_date_str = pub_date_tag.get('content')
            if pub_date_str:
                try:
                    pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                    if timezone.is_naive(pub_date):
                        pub_date = timezone.make_aware(pub_date)
                except (ValueError, AttributeError):
                    pub_date = timezone.now()

        if not pub_date:
            pub_date = timezone.now()

        # Extract main content from paragraph divs with class 'article-body-module__paragraph__Ts-yF'
        content_text = []
        content_elements = soup.find_all(class_='article-body-module__paragraph__Ts-yF')
        print(f"Found {len(content_elements)} paragraph elements")

        for element in content_elements:
            text = element.get_text(separator=' ', strip=True)
            if text and len(text) > 20:
                content_text.append(text)
                if len(content_text) <= 5:
                    print(f"Added text: {text[:80]}...")

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image from img with data-testid="EagerImage"
        image_url = None
        image_tag = soup.find('img', attrs={'data-testid': 'EagerImage'})
        if image_tag:
            image_url = image_tag.get('src')
            print(f"Found image URL: {image_url}")

        # Fallback to og:image if no featured image found
        if not image_url or (image_url and 'data:image' in image_url):
            og_image_tag = soup.find('meta', property='og:image')
            if og_image_tag:
                image_url = og_image_tag.get('content')
                print(f"Found og:image URL: {image_url}")

        # Extract topics using LLM
        topics = []
        if content:
            from ..utils import extract_topics_with_llm
            topics = extract_topics_with_llm(content)

        # Build result dictionary
        result = {
            'title': title,
            'url': url,
            'pub_date': pub_date,
            'content': content,
            'image_url': image_url,
            'topics': topics
        }

        print(f"Extracted - title={result['title']}, url={result['url']}, "
              f"content_length={len(content) if content else 0}, image_url={bool(image_url)}")

        return result
