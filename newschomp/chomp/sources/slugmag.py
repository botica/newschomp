import random
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from .base import NewsSource


class SlugMagSource(NewsSource):
    """Slug Magazine (Salt Lake City) article source implementation"""

    # Category pages to scrape
    CATEGORY_PAGES = [
        'https://www.slugmag.com/category/music/',
        'https://www.slugmag.com/category/arts/',
        'https://www.slugmag.com/events/',
        'https://www.slugmag.com/category/community/',
    ]

    @property
    def name(self):
        return "Slug Magazine"

    @property
    def source_key(self):
        return "slugmag"

    @property
    def latitude(self):
        return 40.7608

    @property
    def longitude(self):
        return -111.8910

    @property
    def city(self):
        return "Salt Lake City, UT"

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
        Get article URLs from a randomly selected category page.
        Tries other pages if the first one fails.

        Args:
            query: Not used for this source (can be None)

        Returns:
            list: List of article URLs from the category
        """
        import requests

        # Shuffle category pages to randomly pick one
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

                # Check if this is the events page
                is_events_page = '/events/' in category_url
                article_urls = []

                if is_events_page:
                    # Events page: links have class 'wpem-event-action-url'
                    event_links = soup.find_all('a', class_='wpem-event-action-url')
                    print(f"Found {len(event_links)} event links on page")

                    for link in event_links:
                        href = link.get('href', '')
                        if href:
                            # Normalize URL
                            if href.startswith('/'):
                                href = f"https://www.slugmag.com{href}"
                            elif not href.startswith('http'):
                                href = f"https://www.slugmag.com/{href}"
                            article_urls.append(href)
                else:
                    # Regular category pages: link is an a tag in h4 with class 'card-title'
                    card_titles = soup.find_all('h4', class_='card-title')
                    print(f"Found {len(card_titles)} card titles on page")

                    for title_h4 in card_titles:
                        link = title_h4.find('a', href=True)
                        if link:
                            href = link.get('href', '')
                            # Normalize URL
                            if href.startswith('/'):
                                href = f"https://www.slugmag.com{href}"
                            elif not href.startswith('http'):
                                href = f"https://www.slugmag.com/{href}"
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
                continue

        print("All category pages failed or returned no articles")
        return []

    def extract(self, html_string):
        """
        Extract Slug Magazine article data from HTML string.

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
        url = url_tag.get('href') if url_tag else None
        if not url:
            og_url = soup.find('meta', property='og:url')
            url = og_url.get('content') if og_url else None

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

        # Determine if this is an event page or regular article
        # Event pages have div with class 'wpem-single-event-body-content'
        event_content = soup.find('div', class_='wpem-single-event-body-content')
        is_event_page = event_content is not None

        # Extract content
        content_text = []
        if is_event_page:
            # Event page: content is in div with class 'wpem-single-event-body-content'
            print("Detected event page")
            if event_content:
                paragraphs = event_content.find_all('p')
                print(f"Found {len(paragraphs)} paragraphs in event content")
                for para in paragraphs:
                    para_text = para.get_text(separator=' ', strip=True)
                    if para_text and len(para_text) > 20:
                        content_text.append(para_text)
                # If no paragraphs, get all text from the div
                if not content_text:
                    all_text = event_content.get_text(separator='\n', strip=True)
                    if all_text and len(all_text) > 20:
                        content_text.append(all_text)
        else:
            # Regular article: content is in all p tags within div class 'entry-content'
            print("Detected regular article page")
            content_area = soup.find('div', class_='entry-content')
            if content_area:
                paragraphs = content_area.find_all('p')
                print(f"Found {len(paragraphs)} paragraphs in content area")
                for para in paragraphs:
                    para_text = para.get_text(separator=' ', strip=True)
                    if para_text and len(para_text) > 20:
                        content_text.append(para_text)
            else:
                print("No content area found with class 'entry-content'")

        content = '\n'.join(content_text) if content_text else None
        print(f"Final content length: {len(content) if content else 0}")

        # Extract image
        image_url = None
        if is_event_page:
            # Event page: image is in div with class 'wpem-event-single-image'
            image_container = soup.find('div', class_='wpem-event-single-image')
            if image_container:
                image_tag = image_container.find('img')
                if image_tag:
                    image_url = image_tag.get('src') or image_tag.get('data-src')
        else:
            # Regular article: image has class 'wp-post-image'
            image_tag = soup.find('img', class_='wp-post-image')
            if image_tag:
                image_url = image_tag.get('src') or image_tag.get('data-src')

        # Fallback to og:image if no image found
        if not image_url:
            og_image = soup.find('meta', property='og:image')
            if og_image:
                image_url = og_image.get('content')

        # Normalize image URL if relative
        if image_url and image_url.startswith('/'):
            image_url = f"https://www.slugmag.com{image_url}"

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
