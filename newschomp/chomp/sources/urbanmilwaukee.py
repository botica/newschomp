import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class UrbanMilwaukeeSource(NewsSource):
    """Urban Milwaukee article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://urbanmilwaukee.com/food-drink/',
        'https://urbanmilwaukee.com/arts-entertainment/',
    ]

    @property
    def name(self):
        return "Urban Milwaukee"

    @property
    def source_key(self):
        return "urbanmilwaukee"

    def search(self, query=None):
        """
        Get article URLs from category pages.
        Tries all category pages before giving up.
        Note: This source doesn't use search queries - it browses category pages.

        Args:
            query: Not used for this source (can be None)

        Returns:
            list: List of article URLs from the category, sorted by newest first
        """
        import re

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

                # Parse the page
                soup = BeautifulSoup(response.text, 'html.parser')

                # Different category pages use different class names
                # Try "homepage-post" first (used by arts-entertainment)
                article_divs = soup.find_all('div', class_='homepage-post')

                # If not found, try "wide-story-block" (used by food-drink)
                if not article_divs:
                    article_divs = soup.find_all('div', class_='wide-story-block')

                if not article_divs:
                    print(f"No article divs found on {category_url}, trying next category...")
                    continue

                print(f"Found {len(article_divs)} article divs")

                # Extract article URLs
                article_urls = []
                for article_div in article_divs:
                    # Find any <a> tag with a date pattern in the URL (YYYY/MM/DD)
                    link = article_div.find('a', href=lambda x: x and re.search(r'/\d{4}/\d{2}/\d{2}/', x))

                    if link:
                        article_url = link.get('href')
                        if article_url:
                            # Ensure it's a full URL
                            if not article_url.startswith('http'):
                                article_url = f"https://urbanmilwaukee.com{article_url}"

                            print(f"Found article URL: {article_url}")
                            article_urls.append(article_url)

                if article_urls:
                    print(f"Successfully extracted {len(article_urls)} article URLs")
                    return article_urls
                else:
                    print(f"No article URLs extracted from {category_url}, trying next category...")

            except Exception as e:
                print(f"Error fetching category page {category_url}: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                print("Trying next category page...")
                continue

        print("All category pages failed or returned no articles")
        return []

    def extract(self, html_string):
        """
        Extract Urban Milwaukee article data from HTML string.

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

        # Extract main content from div class="entry"
        content_div = soup.find('div', class_='entry')
        content_text = []

        if content_div:
            # Find all <p> tags within the div
            paragraphs = content_div.find_all('p')
            for para in paragraphs:
                para_text = para.get_text(separator=' ', strip=True)
                if para_text:
                    content_text.append(para_text)

        content = '\n'.join(content_text) if content_text else None

        # Detect paywall - check if content indicates paid membership required
        if content and ('available only to Urban Milwaukee' in content or
                       'Membership is available for $9' in content or
                       'paid members' in content.lower()):
            print(f"PAYWALL DETECTED: Article requires paid membership, skipping")
            return None

        # Extract main image from div class="wp-caption"
        image_url = None
        wp_caption_div = soup.find('div', class_='wp-caption')
        if wp_caption_div:
            # Get the direct child div, then find img tag
            for child in wp_caption_div.children:
                if hasattr(child, 'name') and child.name in ['div', 'img']:
                    if child.name == 'img':
                        image_url = child.get('src')
                        break
                    else:
                        # If it's a div, find img within it
                        img_tag = child.find('img')
                        if img_tag:
                            image_url = img_tag.get('src')
                            break

            # Fallback: direct img search if nested approach didn't work
            if not image_url:
                img_tag = wp_caption_div.find('img')
                if img_tag:
                    image_url = img_tag.get('src')

        # Fallback: use og:image meta tag if no image found in wp-caption
        if not image_url:
            og_image_tag = soup.find('meta', property='og:image')
            if og_image_tag:
                image_url = og_image_tag.get('content')

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
