from .base import NewsSource
from .apnews import APNewsSource
from .bbc import BBCSource

# Registry of available news sources
NEWS_SOURCES = {
    'apnews': APNewsSource,
    'bbc': BBCSource,
}

def get_source(source_name):
    """
    Get a news source instance by name.

    Args:
        source_name: Name of the news source (e.g., 'apnews')

    Returns:
        NewsSource instance or None if source not found
    """
    source_class = NEWS_SOURCES.get(source_name.lower())
    if source_class:
        return source_class()
    return None
