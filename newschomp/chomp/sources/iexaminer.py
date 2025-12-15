import re
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class IExaminerSource(NewsSource):
    """iExaminer (Seattle) article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://iexaminer.org/category/arts/',
    ]

    @property
    def name(self):
        return "iExaminer"

    @property
    def source_key(self):
        return "iexaminer"

    @property
    def latitude(self):
        return 47.6062

    @property
    def longitude(self):
        return -122.3321

    @property
    def city(self):
        return "Seattle, WA"

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
                    print('Article element not found, continuing...')

                html = page.content()
                browser.close()
                return html
        except Exception as e:
            print(f"Error fetching article with Playwright: {e}")
            raise

    def search(self, query=None):
        """
        Get article URLs from category pages using Playwright.
        Articles are sorted by newest first on the category page.
        Article links have class 'td-image-wrap'.

        Args:
            query: Not used for this source (can be None)

        Returns:
            list: List of article URLs from the category
        """
        from playwright.sync_api import sync_playwright

        for category_url in self.CATEGORY_PAGES:
            print(f"Fetching articles from category: {category_url}")

            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(category_url, wait_until='networkidle', timeout=30000)

                    # Wait for article links to appear
                    try:
                        page.wait_for_selector('a.td-image-wrap', timeout=10000)
                    except:
                        print("No td-image-wrap links found, continuing...")

                    html = page.content()
                    browser.close()

                # Parse the HTML
                soup = BeautifulSoup(html, 'html.parser')

                # Find article links with class 'td-image-wrap'
                article_urls = []
                article_links = soup.find_all('a', class_='td-image-wrap')
                print(f"Found {len(article_links)} links with class 'td-image-wrap'")

                for link in article_links:
                    href = link.get('href')
                    if href and 'iexaminer.org' in href:
                        article_urls.append(href)

                # Remove duplicates while preserving order (newest first)
                seen = set()
                unique_urls = []
                for url in article_urls:
                    if url not in seen:
                        seen.add(url)
                        unique_urls.append(url)

                if unique_urls:
                    print(f"Found {len(unique_urls)} unique article URLs")
                    return unique_urls
                else:
                    print(f"No articles found on {category_url}")

            except Exception as e:
                print(f"Error fetching category page {category_url}: {type(e).__name__}: {e}")
                continue

        print("All category pages failed or returned no articles")
        return []

    def extract(self, html_string):
        """
        Extract iExaminer article data from HTML string.

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

        # Extract main content from p tags within the article tag
        content_text = []
        article_tag = soup.find('article')

        print(f"Found article tag: {bool(article_tag)}")

        if article_tag:
            # Get all p tags within the article
            for p_tag in article_tag.find_all('p'):
                p_text = p_tag.get_text(separator=' ', strip=True)
                # Skip very short paragraphs (likely navigation or metadata)
                if p_text and len(p_text) > 20:
                    content_text.append(p_text)
                    if len(content_text) <= 5:  # Show first 5
                        print(f"Added text: {p_text[:80]}...")

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image - try class pattern 'wp-image-*' first
        image_url = None

        # Look for image with class matching wp-image-* pattern (WordPress image)
        if article_tag:
            image_tag = article_tag.find('img', class_=re.compile(r'wp-image-\d+'))
            if image_tag:
                image_url = (image_tag.get('src') or
                            image_tag.get('data-src') or
                            (image_tag.get('srcset', '').split()[0] if image_tag.get('srcset') else None))
                print(f"Found wp-image URL: {image_url}")

        # Fallback to og:image if no featured image found
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
