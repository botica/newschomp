import random
import re
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class STLMagSource(NewsSource):
    """STL Magazine article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://www.stlmag.com/dining/',
        'https://www.stlmag.com/culture/',
        'https://www.stlmag.com/health/',
    ]

    @property
    def name(self):
        return "STL Magazine"

    @property
    def source_key(self):
        return "stlmag"

    def fetch(self, url):
        """
        Fetch HTML content from a URL with User-Agent header.

        Args:
            url: URL to fetch

        Returns:
            str: HTML content as string
        """
        import requests
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text

    def search(self, query=None):
        """
        Get article URLs from category pages.
        Tries all category pages before giving up.
        Note: This source doesn't use search queries - it browses category pages.

        Args:
            query: Not used for this source (can be None)

        Returns:
            list: List of article URLs from the category
        """
        import requests

        # Shuffle category pages to randomize which one we try first
        category_pages = self.CATEGORY_PAGES.copy()
        random.shuffle(category_pages)

        for category_url in category_pages:
            print(f"Fetching articles from category: {category_url}")

            try:
                # Fetch the category page
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                }
                response = requests.get(category_url, headers=headers)
                response.raise_for_status()
                html = response.text

                # Parse the HTML
                soup = BeautifulSoup(html, 'html.parser')

                # Find all article cards with class 'c-article-card'
                article_cards = soup.find_all('article', class_='c-article-card')
                print(f"Found {len(article_cards)} article cards on page")

                article_urls = []
                for card in article_cards:
                    # Find the h2 with class 'c-article-card__title'
                    title_h2 = card.find('h2', class_='c-article-card__title')
                    if title_h2:
                        # Find the link within the h2
                        link = title_h2.find('a', href=True)
                        if link:
                            href = link.get('href', '')

                            # Normalize URL - handle relative paths
                            if href.startswith('/'):
                                href = f"https://www.stlmag.com{href}"
                            elif not href.startswith('http'):
                                href = f"https://www.stlmag.com/{href}"

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
        Extract STL Magazine article data from HTML string.

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

        # Extract main content from paragraphs within content container
        # Try wp-block-post-content first (new WordPress block editor), then entry-content (legacy)
        content_text = []
        content_area = soup.find('div', class_='wp-block-post-content')
        if not content_area:
            content_area = soup.find('div', class_='entry-content')

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
            print("No content area found with class 'entry-content'")

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image with class 'c-single-post-image'
        image_url = None
        image_tag = soup.find('img', class_='c-single-post-image')
        if image_tag:
            image_url = image_tag.get('src') or image_tag.get('data-src')
            # Normalize image URL if relative
            if image_url and image_url.startswith('/'):
                image_url = f"https://www.stlmag.com{image_url}"
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
