from .base import NewsSource
from .apnews import APNewsSource
from .austinchronicle import AustinChronicleSource
from .bbc import BBCSource
from .doorcountypulse import DoorCountyPulseSource
from .urbanmilwaukee import UrbanMilwaukeeSource
from .stlmag import STLMagSource
from .blockclubchicago import BlockClubChicagoSource
from .gothamist import GothamistSource
from .magazine303 import Magazine303Source
from .iexaminer import IExaminerSource
from .gambit import GambitSource
from .reuters import ReutersSource
from .slugmag import SlugMagSource
from .folioweekly import FolioWeeklySource

# Registry of available news sources
NEWS_SOURCES = {
    'apnews': APNewsSource,
    'austinchronicle': AustinChronicleSource,
    'bbc': BBCSource,
    'doorcountypulse': DoorCountyPulseSource,
    'urbanmilwaukee': UrbanMilwaukeeSource,
    'stlmag': STLMagSource,
    'blockclubchicago': BlockClubChicagoSource,
    'gothamist': GothamistSource,
    '303magazine': Magazine303Source,
    'iexaminer': IExaminerSource,
    'gambit': GambitSource,
    'reuters': ReutersSource,
    'slugmag': SlugMagSource,
    'folioweekly': FolioWeeklySource,
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


# Local sources with location data
LOCAL_SOURCES = [
    'austinchronicle', 'doorcountypulse', 'urbanmilwaukee', 'stlmag',
    'blockclubchicago', 'gothamist', '303magazine', 'iexaminer',
    'gambit', 'slugmag', 'folioweekly'
]


def get_local_sources_with_locations():
    """
    Get all local news sources with their location data.

    Returns:
        list: List of dicts with source_key, name, latitude, longitude, city
    """
    sources = []
    for source_key in LOCAL_SOURCES:
        source = get_source(source_key)
        if source and source.latitude and source.longitude:
            sources.append({
                'source_key': source.source_key,
                'name': source.name,
                'latitude': source.latitude,
                'longitude': source.longitude,
                'city': source.city,
            })
    return sources


def get_source_for_url(url):
    """
    Detect the appropriate source for a given URL based on domain.

    Args:
        url: Article URL

    Returns:
        NewsSource instance or None if no matching source found
    """
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Map domains to source keys
    domain_map = {
        'bbc.com': 'bbc',
        'www.bbc.com': 'bbc',
        'bbc.co.uk': 'bbc',
        'www.bbc.co.uk': 'bbc',
        'apnews.com': 'apnews',
        'www.apnews.com': 'apnews',
        'reuters.com': 'reuters',
        'www.reuters.com': 'reuters',
        'austinchronicle.com': 'austinchronicle',
        'www.austinchronicle.com': 'austinchronicle',
        'doorcountypulse.com': 'doorcountypulse',
        'www.doorcountypulse.com': 'doorcountypulse',
        'urbanmilwaukee.com': 'urbanmilwaukee',
        'www.urbanmilwaukee.com': 'urbanmilwaukee',
        'stlmag.com': 'stlmag',
        'www.stlmag.com': 'stlmag',
        'blockclubchicago.org': 'blockclubchicago',
        'www.blockclubchicago.org': 'blockclubchicago',
        'gothamist.com': 'gothamist',
        'www.gothamist.com': 'gothamist',
        '303magazine.com': '303magazine',
        'www.303magazine.com': '303magazine',
        'iexaminer.org': 'iexaminer',
        'www.iexaminer.org': 'iexaminer',
        'thegambit.com': 'gambit',
        'www.thegambit.com': 'gambit',
        'slugmag.com': 'slugmag',
        'www.slugmag.com': 'slugmag',
        'folioweekly.com': 'folioweekly',
        'www.folioweekly.com': 'folioweekly',
    }

    source_key = domain_map.get(domain)
    if source_key:
        return get_source(source_key)
    return None


def find_nearest_source(user_lat, user_lng):
    """
    Find the nearest local news source to the user's location.

    Args:
        user_lat: User's latitude
        user_lng: User's longitude

    Returns:
        dict: Source info with distance, or None if no sources available
    """
    import math

    def haversine_distance(lat1, lon1, lat2, lon2):
        """Calculate distance between two points in km using Haversine formula."""
        R = 6371  # Earth's radius in km
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return R * c

    sources = get_local_sources_with_locations()
    if not sources:
        return None

    nearest = None
    min_distance = float('inf')

    for source in sources:
        distance = haversine_distance(
            user_lat, user_lng,
            source['latitude'], source['longitude']
        )
        if distance < min_distance:
            min_distance = distance
            nearest = {**source, 'distance_km': round(distance, 2)}

    return nearest
