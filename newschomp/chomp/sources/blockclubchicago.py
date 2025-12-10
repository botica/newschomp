import random
import re
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource

class BlockClubChicagoSource(NewsSource):
    """Block Club Chicago article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://blockclubchicago.org/arts-culture/',
    ]

    @property
    def name(self):
        return "Block Club Chicago"

    @property
    def source_key(self):
        return "blockclubchicago"

    def search(self, query=None):
        """
        Get article URLs from category pages.
        Tries all category pages before giving up.
        Note: This source doesn't use search queries - it browses the category page.

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
                response = requests.get(category_url)
                response.raise_for_status()
                html = response.text

                # Parse the HTML
                soup = BeautifulSoup(html, 'html.parser')

                # Find ALL anchor tags with article URLs (date pattern in URL)
                # This catches articles regardless of their container element
                article_urls = []
                all_links = soup.find_all('a', href=True)
                print(f"Found {len(all_links)} total links on page")

                for link in all_links:
                    href = link.get('href')
                    # Match URLs with date pattern like /2025/12/09/ (article URLs)
                    if href and re.search(r'blockclubchicago\.org/\d{4}/\d{2}/\d{2}/', href):
                        article_urls.append(href)

                print(f"Found {len(article_urls)} article links before deduplication")

                # Remove duplicates while preserving order
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
                    print(f"No articles found on {category_url}, trying next category...")

            except Exception as e:
                print(f"Error fetching category page {category_url}: {type(e).__name__}: {e}")
                print("Trying next category page...")
                continue

        print("All category pages failed or returned no articles")
        return []

    def extract(self, html_string):
        """
        Extract Block Club Chicago article data from HTML string.

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

        # Extract main content from div with class 'entry-content'
        content_text = []
        entry_content = soup.find('div', class_='entry-content')

        print(f"Found entry-content div: {bool(entry_content)}")

        if entry_content:
            # Get all text content from the entry-content div
            # Extract all text-containing elements (p, h2, h3, li, etc.)
            for elem in entry_content.find_all(['p', 'h2', 'h3', 'h4', 'li']):
                elem_text = elem.get_text(separator=' ', strip=True)
                # Skip very short elements (likely navigation or metadata)
                if elem_text and len(elem_text) > 20:
                    content_text.append(elem_text)
                    if len(content_text) <= 5:  # Show first 5
                        print(f"Added text: {elem_text[:80]}...")

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image - img with class starting with 'attachment-newspack-featured-image'
        image_url = None
        # Find img tag with class containing 'attachment-newspack-featured-image'
        image_tag = soup.find('img', class_=re.compile(r'attachment-newspack-featured-image'))

        if image_tag:
            # Try src first, then srcset, then data-src
            image_url = (image_tag.get('src') or
                        image_tag.get('data-src') or
                        (image_tag.get('srcset', '').split()[0] if image_tag.get('srcset') else None))
            print(f"Found image URL: {image_url}")

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
