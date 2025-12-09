from .base import NewsSource
from .apnews import APNewsSource
from .austinchronicle import AustinChronicleSource
from .bbc import BBCSource
from .doorcountypulse import DoorCountyPulseSource
from .urbanmilwaukee import UrbanMilwaukeeSource
from .lataco import LATacoSource
from .stlmag import STLMagSource
from .blockclubchicago import BlockClubChicagoSource
from .gothamist import GothamistSource
from .miamiliving import MiamiLivingSource

# Registry of available news sources
NEWS_SOURCES = {
    'apnews': APNewsSource,
    'austinchronicle': AustinChronicleSource,
    'bbc': BBCSource,
    'doorcountypulse': DoorCountyPulseSource,
    'urbanmilwaukee': UrbanMilwaukeeSource,
    'lataco': LATacoSource,
    'stlmag': STLMagSource,
    'blockclubchicago': BlockClubChicagoSource,
    'gothamist': GothamistSource,
    'miamiliving': MiamiLivingSource,
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
