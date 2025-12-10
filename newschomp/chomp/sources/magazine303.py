from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class Magazine303Source(NewsSource):
    """303 Magazine (Denver) article source implementation"""

    @property
    def name(self):
        return "303 Magazine"

    @property
    def source_key(self):
        return "303magazine"

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
        Get article URLs from the current month's archive page.
        Note: This source doesn't use search queries - it browses the monthly archive.

        Args:
            query: Not used for this source (can be None)

        Returns:
            list: List of article URLs from the current month's archive
        """
        import requests

        # Use current month's archive page for more articles
        now = datetime.now()
        archive_url = f"https://303magazine.com/{now.year}/{now.month:02d}/"
        print(f"Fetching articles from archive: {archive_url}")

        try:
            # Fetch the archive page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            response = requests.get(archive_url, headers=headers)
            response.raise_for_status()
            html = response.text

            # Parse the HTML
            soup = BeautifulSoup(html, 'html.parser')

            article_urls = []

            # Method 1: Find entry titles (cs-entry__title class)
            entry_titles = soup.find_all(class_='cs-entry__title')
            print(f"Found {len(entry_titles)} entry titles on page")

            for title_elem in entry_titles:
                link = title_elem.find('a', href=True)
                if link:
                    href = link.get('href', '')
                    if '303magazine.com' in href and '/20' in href:
                        article_urls.append(href)

            # Method 2: Find all links that look like article URLs
            if not article_urls:
                all_links = soup.find_all('a', href=True)
                print(f"Fallback: checking {len(all_links)} links on page")
                for link in all_links:
                    href = link.get('href', '')
                    # Match pattern like https://303magazine.com/2025/12/article-slug/
                    if '303magazine.com/20' in href and href.count('/') >= 5:
                        article_urls.append(href)

            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in article_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)

            print(f"Found {len(unique_urls)} unique article URLs")
            for url in unique_urls[:10]:
                print(f"  {url}")

            return unique_urls

        except Exception as e:
            print(f"Error fetching archive page: {type(e).__name__}: {e}")
            return []

    def extract(self, html_string):
        """
        Extract 303 Magazine article data from HTML string.

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

        # Extract main content from all paragraphs
        content_text = []
        paragraphs = soup.find_all('p')
        print(f"Found {len(paragraphs)} paragraphs on page")

        for para in paragraphs:
            para_text = para.get_text(separator=' ', strip=True)
            # Skip very short paragraphs (likely navigation or metadata)
            if para_text and len(para_text) > 20:
                content_text.append(para_text)

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract main image - prefer og:image as it's most reliable
        image_url = None
        og_image = soup.find('meta', property='og:image')
        if og_image:
            image_url = og_image.get('content')
            print(f"Found og:image: {image_url}")

        # Fallback to figure tag if no og:image
        if not image_url:
            figure_tag = soup.find('figure')
            if figure_tag:
                img_tag = figure_tag.find('img')
                if img_tag:
                    image_url = img_tag.get('src') or img_tag.get('data-src')
                    print(f"Found image in figure: {image_url}")

        # Normalize image URL if relative
        if image_url and image_url.startswith('/'):
            image_url = f"https://303magazine.com{image_url}"

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
