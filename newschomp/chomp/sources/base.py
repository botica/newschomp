from abc import ABC, abstractmethod


class NewsSource(ABC):
    """
    Base class for all news sources.
    Each news source should implement the methods below to provide
    a consistent interface for searching and extracting articles.
    """

    @property
    @abstractmethod
    def name(self):
        """Return the display name of the news source"""
        pass

    @property
    @abstractmethod
    def source_key(self):
        """Return the unique key identifier for this source"""
        pass

    @abstractmethod
    def search(self, query):
        """
        Search for articles matching the query.

        Args:
            query: Search query string

        Returns:
            str: URL of the first article found, or None if no results
        """
        pass

    @abstractmethod
    def extract(self, html_string):
        """
        Extract article data from HTML content.

        Args:
            html_string: HTML content as string

        Returns:
            dict: Dictionary containing:
                - title: Article title
                - url: Article URL
                - pub_date: Publication date (datetime object)
                - content: Article text content
                - image_url: Main image URL (optional)
        """
        pass

    def fetch(self, url):
        """
        Fetch HTML content from a URL.
        Can be overridden by sources that need special fetching (e.g., Playwright).

        Args:
            url: URL to fetch

        Returns:
            str: HTML content as string
        """
        import requests
        response = requests.get(url)
        response.raise_for_status()
        return response.text

    def search_and_extract(self, query):
        """
        Search for an article and extract its data.
        This is a convenience method that combines search and extract.

        Args:
            query: Search query string

        Returns:
            dict: Extracted article data or None if search/extraction fails
        """
        import requests

        # Get article URL from search
        article_url = self.search(query)
        if not article_url:
            return None

        # Fetch article page
        response = requests.get(article_url)
        response.raise_for_status()

        # Extract content
        return self.extract(response.text)
