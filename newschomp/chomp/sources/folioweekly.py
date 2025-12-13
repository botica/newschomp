import random
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class FolioWeeklySource(NewsSource):
    """Folio Weekly (Jacksonville, FL) article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://folioweekly.com/category/entertainment/',
        'https://folioweekly.com/category/lifestyle/',
    ]

    @property
    def name(self):
        return "Folio Weekly"

    @property
    def source_key(self):
        return "folioweekly"

    def fetch(self, url):
        """
        Fetch HTML content from a URL using Playwright for JavaScript rendering.
        """
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=30000)

                # Wait for article content to load
                try:
                    page.wait_for_selector('.entry-content, article', timeout=10000)
                except:
                    print('Article element not found, continuing...')

                # Additional wait for JS to render
                page.wait_for_timeout(2000)

                html = page.content()
                browser.close()
                return html
        except Exception as e:
            print(f"Error fetching article with Playwright: {e}")
            raise

    def search(self, query=None):
        """
        Get article URLs from category pages using Playwright.
        Articles are in <article> tags, link is direct child of <h2>.

        Returns:
            list: List of article URLs
        """
        from playwright.sync_api import sync_playwright

        # Shuffle category pages to randomize
        category_pages = self.CATEGORY_PAGES.copy()
        random.shuffle(category_pages)

        for category_url in category_pages:
            print(f"Fetching articles from category: {category_url}")

            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    page = context.new_page()
                    page.goto(category_url, wait_until='domcontentloaded', timeout=30000)

                    # Wait for articles to load
                    try:
                        page.wait_for_selector('article', timeout=10000)
                    except:
                        print("No article elements found via selector, waiting for page load...")

                    # Additional wait for JS to render content
                    page.wait_for_timeout(3000)

                    html = page.content()
                    print(f"Page HTML length: {len(html)}")
                    browser.close()

                soup = BeautifulSoup(html, 'html.parser')

                # Find all article tags
                articles = soup.find_all('article')
                print(f"Found {len(articles)} article tags on page")

                article_urls = []
                for article in articles:
                    # Find h2 tag and get direct child link
                    h2 = article.find('h2')
                    if h2:
                        link = h2.find('a', href=True)
                        if link:
                            href = link.get('href', '')

                            # Normalize URL
                            if href.startswith('/'):
                                href = f"https://folioweekly.com{href}"
                            elif not href.startswith('http'):
                                href = f"https://folioweekly.com/{href}"

                            article_urls.append(href)

                # Remove duplicates while preserving order
                seen = set()
                unique_urls = []
                for url in article_urls:
                    if url not in seen:
                        seen.add(url)
                        unique_urls.append(url)

                if unique_urls:
                    print(f"Found {len(unique_urls)} unique article URLs")
                    for url in unique_urls[:10]:
                        print(f"  {url}")
                    return unique_urls
                else:
                    print(f"No articles found on {category_url}, trying next category...")

            except Exception as e:
                print(f"Error fetching category page {category_url}: {type(e).__name__}: {e}")
                print("Trying next category page...")
                continue

        print("All category pages failed or returned no articles")
        return []

    def extract(self, html_string):
        """
        Extract Folio Weekly article data from HTML string.

        Returns:
            dict: Dictionary containing title, url, pub_date, content, image_url, and topics
        """
        soup = BeautifulSoup(html_string, 'html.parser')

        # Extract title from og:title meta tag
        title_tag = soup.find('meta', property='og:title')
        title = title_tag.get('content') if title_tag else None

        # Extract URL from canonical link
        url_tag = soup.find('link', rel='canonical')
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

        # Extract main content from div with class 'entry-content'
        content_text = []
        content_area = soup.find('div', class_='entry-content')

        print(f"Found content_area: {bool(content_area)}")

        if content_area:
            # Get all text content from entry-content
            paragraphs = content_area.find_all('p')
            print(f"Found {len(paragraphs)} paragraphs in content area")

            for para in paragraphs:
                para_text = para.get_text(separator=' ', strip=True)
                # Skip very short paragraphs
                if para_text and len(para_text) > 20:
                    content_text.append(para_text)
                    print(f"Added paragraph: {para_text[:80]}...")
        else:
            print("No content area found with class 'entry-content'")

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image with class 'wp-post-image'
        image_url = None
        raw_image_url = None

        image_tag = soup.find('img', class_='wp-post-image')
        if image_tag:
            raw_image_url = image_tag.get('src') or image_tag.get('data-src')
            # Normalize image URL if relative
            if raw_image_url and raw_image_url.startswith('/'):
                raw_image_url = f"https://folioweekly.com{raw_image_url}"
            print(f"Found wp-post-image URL: {raw_image_url}")

        # Fallback to og:image
        if not raw_image_url:
            og_image_tag = soup.find('meta', property='og:image')
            if og_image_tag:
                raw_image_url = og_image_tag.get('content')
                print(f"Found og:image URL: {raw_image_url}")

        # Fetch image with proper Referer and convert to base64 data URL
        if raw_image_url:
            try:
                import requests
                import base64
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': 'https://folioweekly.com/',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                }
                img_response = requests.get(raw_image_url, headers=headers, timeout=10)
                if img_response.status_code == 200:
                    content_type = img_response.headers.get('Content-Type', 'image/jpeg')
                    img_base64 = base64.b64encode(img_response.content).decode('utf-8')
                    image_url = f"data:{content_type};base64,{img_base64}"
                    print(f"Successfully converted image to base64 data URL")
                else:
                    print(f"Failed to fetch image: HTTP {img_response.status_code}")
            except Exception as e:
                print(f"Error fetching image: {e}")

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
