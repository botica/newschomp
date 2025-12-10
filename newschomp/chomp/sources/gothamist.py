import random
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource

class GothamistSource(NewsSource):
    """The Gothamist article source implementation - Arts & Entertainment section"""

    # Arts & Entertainment category pages
    CATEGORY_PAGES = [
        'https://gothamist.com/arts-entertainment/',
    ]

    @property
    def name(self):
        return "The Gothamist"

    @property
    def source_key(self):
        return "gothamist"

    def search(self, query=None):
        """
        Get article URLs from The Gothamist Arts & Entertainment section.
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

                # Find article links using card-title-link class
                article_urls = []

                # Find all links with card-title-link class
                for link in soup.find_all('a', class_='card-title-link'):
                    href = link.get('href')
                    if href:
                        # Convert relative URLs to absolute URLs
                        if href.startswith('/'):
                            href = f"https://gothamist.com{href}"
                        if href.startswith('http'):
                            article_urls.append(href)
                            print(f"Found article: {href}")

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
        Extract Gothamist article data from HTML string.

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

        # Extract main content
        content_text = []

        # Find the main content div
        content_div = soup.find('div', class_='content')

        print(f"Found content div: {bool(content_div)}")

        if content_div:
            # Get all text content from paragraphs and headings
            for elem in content_div.find_all(['p', 'h2', 'h3', 'h4', 'li']):
                elem_text = elem.get_text(separator=' ', strip=True)
                # Skip very short elements (likely navigation or metadata)
                if elem_text and len(elem_text) > 20:
                    content_text.append(elem_text)
                    if len(content_text) <= 5:  # Show first 5
                        print(f"Added text: {elem_text[:80]}...")

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image from og:image
        image_url = None
        og_image_tag = soup.find('meta', property='og:image')
        if og_image_tag:
            image_url = og_image_tag.get('content')
            print(f"Found og:image URL: {image_url}")

        # Also try to find featured image
        if not image_url:
            # Try various common image selectors
            image_tag = (soup.find('img', class_='featured-image') or
                        soup.find('img', class_='wp-post-image') or
                        soup.find('figure', class_='featured-image'))

            if image_tag:
                if image_tag.name == 'img':
                    image_url = (image_tag.get('src') or
                               image_tag.get('data-src') or
                               (image_tag.get('srcset', '').split()[0] if image_tag.get('srcset') else None))
                else:
                    # If it's a figure, find img inside
                    img = image_tag.find('img')
                    if img:
                        image_url = (img.get('src') or
                                   img.get('data-src') or
                                   (img.get('srcset', '').split()[0] if img.get('srcset') else None))
                print(f"Found featured image URL: {image_url}")

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
