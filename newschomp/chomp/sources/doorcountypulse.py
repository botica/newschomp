import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class DoorCountyPulseSource(NewsSource):
    """Door County Pulse article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://doorcountypulse.com/food-and-drink/',
        'https://doorcountypulse.com/entertainment/',
        'https://doorcountypulse.com/outdoor/',
    ]

    @property
    def name(self):
        return "Door County Pulse"

    @property
    def source_key(self):
        return "doorcountypulse"

    def search(self, query=None):
        """
        Get article URLs from a random category page.
        Note: This source doesn't use search queries - it browses category pages.

        Args:
            query: Not used for this source (can be None)

        Returns:
            list: List of article URLs from a random category, sorted by newest first
        """
        # Pick a random category
        category_url = random.choice(self.CATEGORY_PAGES)
        print(f"Fetching articles from category: {category_url}")

        try:
            # Fetch the category page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            response = requests.get(category_url, headers=headers)
            response.raise_for_status()

            # Parse the page
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all article elements with class containing 'post'
            # Articles are sorted by newest first on the page
            # Note: The actual HTML uses <li> elements, not <div>
            article_elements = soup.find_all('li', class_=lambda x: x and 'post' in x)

            if not article_elements:
                print("No article elements found on category page")
                return []

            print(f"Found {len(article_elements)} article elements")

            # Extract article URLs
            article_urls = []
            for article_elem in article_elements:
                # Find <p class="hentry__title"> containing the article link
                # Note: It's "hentry__title" with double underscores, not "hentry-title"
                title_p = article_elem.find('p', class_='hentry__title')
                if not title_p:
                    continue

                # Find the <a> tag within it
                link_tag = title_p.find('a')
                if not link_tag:
                    continue

                article_url = link_tag.get('href')
                if not article_url:
                    continue

                # Ensure it's a full URL
                if not article_url.startswith('http'):
                    article_url = f"https://doorcountypulse.com{article_url}"

                # Skip podcast articles (only if 'podcast' is at the start of the path)
                # Extract path after base URL
                path = article_url.replace('https://doorcountypulse.com/', '')
                if path.lower().startswith('podcast'):
                    print(f"Skipping podcast URL: {article_url}")
                    continue

                print(f"Found article URL: {article_url}")
                article_urls.append(article_url)

            if not article_urls:
                print("No article URLs extracted from category page")
            else:
                print(f"Successfully extracted {len(article_urls)} article URLs")

            return article_urls

        except Exception as e:
            print(f"Error fetching category page: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def extract(self, html_string):
        """
        Extract Door County Pulse article data from HTML string.

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
        # Look for og:published_time or article:published_time
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

        # Extract main content from <section class="pg-content">
        content_section = soup.find('section', class_='pg-content')
        content_text = []

        if content_section:
            # Find all <p> tags within the section
            paragraphs = content_section.find_all('p')
            for para in paragraphs:
                para_text = para.get_text(separator=' ', strip=True)
                if para_text:
                    content_text.append(para_text)

        content = '\n'.join(content_text) if content_text else None

        # Extract main image from <div class="featured-image">
        image_url = None
        featured_image_div = soup.find('div', class_='featured-image')
        if featured_image_div:
            img_tag = featured_image_div.find('img')
            if img_tag:
                image_url = img_tag.get('src')
                print(f"DEBUG: Found image URL: {image_url}")

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

        print(f"DEBUG: Extracted - title={result['title']}, url={result['url']}, "
              f"content_length={len(content) if content else 0}, image_url={bool(image_url)}")

        return result
