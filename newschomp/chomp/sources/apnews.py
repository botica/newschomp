import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class APNewsSource(NewsSource):
    """AP News article source implementation"""

    @property
    def name(self):
        return "AP News"

    @property
    def source_key(self):
        return "apnews"

    def search(self, query):
        """
        Search AP News and get URLs of article results sorted by relevance.
        Skips non-article pages (videos, galleries, etc.)

        Args:
            query: Search query string

        Returns:
            list: List of article URLs sorted by relevance, or empty list if not found
        """
        # Build search URL - s=0 sorts by relevance
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://apnews.com/search?q={encoded_query}&s=0"

        print(f"Searching AP News: {search_url}")

        # Fetch search results page
        response = requests.get(search_url)
        response.raise_for_status()

        # Parse search results
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find all results with PagePromo-title
        promo_titles = soup.find_all('div', class_='PagePromo-title')
        if not promo_titles:
            print("No search results found")
            return []

        # Collect all valid article URLs
        article_urls = []
        for promo_title in promo_titles:
            link_element = promo_title.find('a', class_='Link')
            if not link_element:
                continue

            article_url = link_element.get('href')
            if not article_url:
                continue

            # Handle relative URLs
            if not article_url.startswith('http'):
                article_url = f"https://apnews.com{article_url}"

            # Check if it's an article URL (not video, gallery, etc.)
            if '/article/' in article_url:
                print(f"Found article URL: {article_url}")
                article_urls.append(article_url)
            else:
                print(f"Skipping non-article URL: {article_url}")

        if not article_urls:
            print("No article URLs found in search results")
        else:
            print(f"Found {len(article_urls)} article URLs sorted by relevance")

        return article_urls

    def extract(self, html_string):
        """
        Extract AP News article data from HTML string.

        Args:
            html_string: HTML content as string

        Returns:
            dict: Dictionary containing title, url, pub_date, content, image_url, and topics
        """
        soup = BeautifulSoup(html_string, 'html.parser')

        # Extract meta tags
        title_tag = soup.find('meta', property='og:title')
        url_tag = soup.find('meta', property='og:url')
        pub_date_tag = soup.find('meta', property='article:published_time')

        # Extract topics from article:tag meta tags
        topics = []
        topic_tags = soup.find_all('meta', property='article:tag')
        for tag in topic_tags:
            topic_content = tag.get('content')
            if topic_content:
                topics.append(topic_content)

        # Remove duplicates while preserving order
        topics = list(dict.fromkeys(topics))

        # Extract content div
        content_div = soup.find('div', class_='RichTextStoryBody RichTextBody')

        # Extract image from first picture tag after Page-content div
        image_url = None
        page_content_div = soup.find('div', class_='Page-content')
        if page_content_div:
            picture_tag = page_content_div.find('picture')
            if picture_tag:
                img_tag = picture_tag.find('img', class_='Image')
                if img_tag:
                    # Try lazy-load attributes first (AP News uses Flickity lazy loading)
                    image_url = (img_tag.get('data-flickity-lazyload') or
                                img_tag.get('src'))

                    # If we got a srcset, extract the first URL
                    if not image_url or image_url.startswith('data:'):
                        srcset = img_tag.get('data-flickity-lazyload-srcset')
                        if srcset:
                            # Extract first URL from srcset (before "1x" or "2x")
                            image_url = srcset.split()[0]

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

        # Build result dictionary
        result = {
            'title': title_tag.get('content') if title_tag else None,
            'url': url_tag.get('content') if url_tag else None,
            'pub_date': pub_date,
            'content': content_div.get_text(strip=True) if content_div else None,
            'image_url': image_url,
            'topics': topics
        }

        return result
