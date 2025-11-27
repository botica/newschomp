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
        Search AP News and get the URL of the first article result.
        Skips non-article pages (videos, galleries, etc.)

        Args:
            query: Search query string

        Returns:
            str: URL of the first article result, or None if not found
        """
        # Build search URL
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://apnews.com/search?q={encoded_query}&s=3"

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
            return None

        # Loop through results to find first valid article URL
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
                return article_url
            else:
                print(f"Skipping non-article URL: {article_url}")

        print("No article URLs found in search results")
        return None

    def extract(self, html_string):
        """
        Extract AP News article data from HTML string.

        Args:
            html_string: HTML content as string

        Returns:
            dict: Dictionary containing title, url, pub_date, content, and image_url
        """
        soup = BeautifulSoup(html_string, 'html.parser')

        # Extract meta tags
        title_tag = soup.find('meta', property='og:title')
        url_tag = soup.find('meta', property='og:url')
        pub_date_tag = soup.find('meta', property='article:published_time')

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
                    image_url = img_tag.get('src')

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
            'image_url': image_url
        }

        return result
