import random
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class MiamiLivingSource(NewsSource):
    """Miami Living Magazine article source implementation - Food/Drink and Culture sections"""

    CATEGORY_PAGES = [
        'https://www.miamilivingmagazine.com/food-drink',
        'https://www.miamilivingmagazine.com/culture',
    ]

    @property
    def name(self):
        return "Miami Living Magazine"

    @property
    def source_key(self):
        return "miamiliving"

    def fetch(self, url):
        """
        Fetch HTML content from a URL using Playwright for JavaScript rendering.

        Args:
            url: URL to fetch

        Returns:
            str: HTML content as string
        """
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until='networkidle', timeout=30000)

                # Wait for article content to load
                try:
                    page.wait_for_selector('article', timeout=10000)
                except:
                    print('Article selector not found, continuing...')

                html = page.content()
                browser.close()
                return html
        except Exception as e:
            print(f"Error fetching article with Playwright: {e}")
            # Fallback to basic fetch
            import requests
            response = requests.get(url)
            response.raise_for_status()
            return response.text

    def search(self, query=None):
        """
        Get article URLs from Miami Living Magazine Food/Drink and Culture sections.
        Uses Playwright for JavaScript rendering (Wix site).

        Args:
            query: Not used for this source (can be None)

        Returns:
            list: List of article URLs from the category
        """
        from playwright.sync_api import sync_playwright

        category_url = random.choice(self.CATEGORY_PAGES)
        print(f"Fetching articles from category: {category_url}")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(category_url, wait_until='networkidle', timeout=30000)

                # Wait for gallery items to load
                try:
                    page.wait_for_selector('.gallery-item-container', timeout=10000)
                except:
                    print('Gallery items not found, continuing...')

                html = page.content()
                browser.close()

            soup = BeautifulSoup(html, 'html.parser')

            article_urls = []

            # Find all gallery-item-container divs
            for container in soup.find_all(class_='gallery-item-container'):
                # Find the <a> tag inside
                link = container.find('a')
                if link:
                    href = link.get('href')
                    if href:
                        # Convert relative URLs to absolute URLs
                        if href.startswith('/'):
                            href = f"https://www.miamilivingmagazine.com{href}"
                        # Only include article URLs (those with /post/)
                        if '/post/' in href:
                            article_urls.append(href)
                            print(f"Found article: {href}")

            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in article_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)

            print(f"Found {len(unique_urls)} unique article URLs")
            return unique_urls

        except Exception as e:
            print(f"Error fetching category page: {type(e).__name__}: {e}")
            return []

    def extract(self, html_string):
        """
        Extract Miami Living Magazine article data from HTML string.

        Args:
            html_string: HTML content as string

        Returns:
            dict: Dictionary containing title, url, pub_date, content, image_url, and topics
        """
        soup = BeautifulSoup(html_string, 'html.parser')

        # Find the article tag
        article = soup.find('article')

        # Extract title from h1
        title = None
        if article:
            h1 = article.find('h1')
            if h1:
                title = h1.get_text(strip=True)

        # Fallback to og:title if no h1 found
        if not title:
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
                       soup.find('meta', property='og:published_time') or \
                       soup.find('time', datetime=True)

        if pub_date_tag:
            if pub_date_tag.name == 'time':
                pub_date_str = pub_date_tag.get('datetime')
            else:
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

        # Extract main content from all p tags within article
        content_text = []
        if article:
            for p in article.find_all('p'):
                p_text = p.get_text(separator=' ', strip=True)
                if p_text and len(p_text) > 10:
                    content_text.append(p_text)

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image from wow-image tag with class 'undefined F5cHb'
        # Use data-pin-media for high resolution, fall back to src
        image_url = None
        wow_image = soup.find('wow-image', class_='undefined F5cHb')
        if wow_image:
            img = wow_image.find('img')
            if img:
                # data-pin-media has the high-res version
                image_url = img.get('data-pin-media') or img.get('src')
                print(f"Found wow-image URL: {image_url}")

        # Fallback to og:image
        if not image_url:
            og_image_tag = soup.find('meta', property='og:image')
            if og_image_tag:
                image_url = og_image_tag.get('content')
                print(f"Found og:image URL: {image_url}")

        # Extract topics using LLM
        topics = []
        if content:
            from ..utils import extract_topics_with_llm
            topics = extract_topics_with_llm(content)

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
