import random
import re
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class GambitSource(NewsSource):
    """Gambit (New Orleans) article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://www.nola.com/gambit/food_drink/',
        'https://www.nola.com/gambit/events/',
        'https://www.nola.com/gambit/music/',
    ]

    @property
    def name(self):
        return "Gambit"

    @property
    def source_key(self):
        return "gambit"

    @property
    def latitude(self):
        return 29.9511

    @property
    def longitude(self):
        return -90.0715

    @property
    def city(self):
        return "New Orleans, LA"

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
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()
                page.goto(url, wait_until='domcontentloaded', timeout=30000)

                # Wait for article content to load
                try:
                    page.wait_for_selector('.asset-body, article', timeout=10000)
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
        Picks a random category page, articles sorted by newest first.
        Article URLs contain 'article_' and end with '.html'.

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
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    page = context.new_page()
                    page.goto(category_url, wait_until='domcontentloaded', timeout=30000)

                    # Wait for page content to load
                    try:
                        page.wait_for_selector('a[href*="article_"]', timeout=10000)
                    except:
                        print("No article links found via selector, waiting for page load...")

                    # Additional wait for JS to render content
                    page.wait_for_timeout(3000)

                    html = page.content()
                    print(f"Page HTML length: {len(html)}")
                    browser.close()

                # Parse the HTML
                soup = BeautifulSoup(html, 'html.parser')

                # Find all links that match the article URL pattern
                # Pattern: contains 'article_' and ends with '.html'
                article_urls = []
                all_links = soup.find_all('a', href=True)
                print(f"Found {len(all_links)} total links on page")

                for link in all_links:
                    href = link.get('href')
                    if href and 'article_' in href and href.endswith('.html'):
                        # Handle relative URLs
                        if href.startswith('/'):
                            href = f"https://www.nola.com{href}"
                        # Only include nola.com/gambit articles
                        if 'nola.com' in href and 'gambit' in href:
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
        Extract Gambit article data from HTML string.

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

        # Extract main content from p tags within .asset-body or article tag
        content_text = []

        # Try .asset-body first (nola.com specific), then fall back to article tag
        content_container = soup.find('div', class_='asset-body') or soup.find('article')

        print(f"Found content container: {bool(content_container)}")

        if content_container:
            # Get all p tags within the content container
            for p_tag in content_container.find_all('p'):
                p_text = p_tag.get_text(separator=' ', strip=True)
                # Skip very short paragraphs (likely navigation or metadata)
                if p_text and len(p_text) > 20:
                    content_text.append(p_text)
                    if len(content_text) <= 5:  # Show first 5
                        print(f"Added text: {p_text[:80]}...")

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image - try multiple approaches
        image_url = None

        # First try: find figure element with image
        figure_tag = soup.find('figure')
        if figure_tag:
            image_tag = figure_tag.find('img')
            if image_tag:
                # Handle lazy loading - check various attributes
                image_url = (
                    image_tag.get('data-src') or
                    image_tag.get('src') or
                    None
                )

                # If still no image, try to parse srcset or data-srcset
                if not image_url or 'data:image' in image_url:
                    srcset = image_tag.get('data-srcset') or image_tag.get('srcset')
                    if srcset:
                        # Get the largest/last URL from srcset
                        src_parts = srcset.split(',')
                        if src_parts:
                            last_src = src_parts[-1].strip().split()[0]
                            if last_src and not last_src.startswith('data:'):
                                image_url = last_src

                print(f"Found image URL from figure: {image_url}")

        # Second try: find any card-image
        if not image_url:
            card_image = soup.find('div', class_=re.compile(r'card-image'))
            if card_image:
                image_tag = card_image.find('img')
                if image_tag:
                    image_url = (
                        image_tag.get('data-src') or
                        image_tag.get('src') or
                        None
                    )
                    print(f"Found image URL from card-image: {image_url}")

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
