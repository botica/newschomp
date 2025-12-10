import random
import re
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource

class LATacoSource(NewsSource):
    """L.A. TACO article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://lataco.com/category/food',
    ]

    @property
    def name(self):
        return "L.A. TACO"

    @property
    def source_key(self):
        return "lataco"

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
                    page.wait_for_selector('article, .entry-content, [class*="content"]', timeout=10000)
                except:
                    print('NO')

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
        Get article URLs from category pages using Playwright for JavaScript rendering.
        Tries all category pages before giving up.
        Note: This source doesn't use search queries - it browses category pages.

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
                    # Launch browser
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()

                    # Navigate to category page
                    page.goto(category_url, wait_until='networkidle', timeout=30000)

                    # Wait for links to appear (indicating content has loaded)
                    try:
                        page.wait_for_selector('a[href*="lataco.com"]', timeout=10000)
                    except:
                        # If no links found, continue anyway
                        print("No links found, continuing with page as-is")

                    # Get the rendered HTML
                    html = page.content()
                    browser.close()

                    # Parse the HTML
                    soup = BeautifulSoup(html, 'html.parser')

                    # Find all links
                    all_links = soup.find_all('a', href=True)
                    print(f"Found {len(all_links)} total links on page")

                    # Debug: Show first 10 links
                    print("First 10 links found:")
                    for i, link in enumerate(all_links[:10]):
                        href = link.get('href', '')
                        text = link.get_text(strip=True)[:50]
                        print(f"  {i+1}. {href} | Text: {text}")

                    # Filter for article links
                    article_urls = []
                    for link in all_links:
                        href = link.get('href', '')

                        if not href or href.startswith('#'):
                            continue

                        # Normalize URL - handle relative paths
                        if href.startswith('/') and not href.startswith('//'):
                            href = f"https://lataco.com{href}"
                        elif href.startswith('//'):
                            href = f"https:{href}"
                        elif not href.startswith('http'):
                            continue

                        # Exclude shop and unwanted pages
                        if ('shop.lataco.com' in href or
                            '/category/' in href or
                            '/tag/' in href or
                            '/author/' in href or
                            '/neighborhoods' in href or
                            '/products' in href or
                            '/members' in href or
                            '/join' in href or
                            '/login' in href or
                            '/sponsor' in href or
                            '/mobile-apps' in href or
                            '/local-business-directory' in href or
                            '/send-us-your-stuff' in href or
                            '/terms-of-service' in href or
                            '/privacy-policy' in href or
                            '/about' in href or
                            href in ['https://lataco.com/', 'https://lataco.com', 'https://www.lataco.com/', 'https://www.lataco.com']):
                            continue

                        # Must be lataco.com domain
                        if 'lataco.com' not in href:
                            continue

                        # Check if it looks like an article (has a meaningful path)
                        path = href.replace('https://lataco.com/', '').replace('https://www.lataco.com/', '')
                        if path and len(path) > 10:  # Articles usually have longer paths
                            article_urls.append(href)

                    # Remove duplicates while preserving order
                    seen = set()
                    unique_urls = []
                    for url in article_urls:
                        if url not in seen:
                            seen.add(url)
                            unique_urls.append(url)

                    if unique_urls:
                        print(f"Found {len(unique_urls)} potential article URLs")
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
        Extract L.A. TACO article data from HTML string.

        Args:
            html_string: HTML content as string

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

        # Extract main content from paragraphs
        # Try to find the main article content area
        content_text = []

        # Look for common WordPress article content selectors
        content_area = soup.find('article') or soup.find('div', class_=re.compile('entry-content|article-content|post-content'))

        print(f"Found content_area: {bool(content_area)}")

        if content_area:
            # Find all <p> tags within the content area
            paragraphs = content_area.find_all('p')
            print(f"Found {len(paragraphs)} paragraphs in content area")

            for para in paragraphs:
                para_text = para.get_text(separator=' ', strip=True)
                # Skip very short paragraphs (likely navigation or metadata)
                if para_text and len(para_text) > 20:
                    content_text.append(para_text)
                    print(f"Added paragraph: {para_text[:80]}...")
        else:
            print("No content area found, trying to find all <p> tags on page")
            # Fallback: try to find any paragraphs on the page
            all_paragraphs = soup.find_all('p')
            print(f"Found {len(all_paragraphs)} total paragraphs on page")

            for para in all_paragraphs:
                para_text = para.get_text(separator=' ', strip=True)
                # Skip very short paragraphs (likely navigation or metadata)
                if para_text and len(para_text) > 20:
                    content_text.append(para_text)
                    if len(content_text) <= 5:  # Show first 5
                        print(f"Added paragraph: {para_text[:80]}...")

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image from og:image
        image_url = None
        og_image_tag = soup.find('meta', property='og:image')
        if og_image_tag:
            image_url = og_image_tag.get('content')
            print(f"Found image URL: {image_url}")

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
