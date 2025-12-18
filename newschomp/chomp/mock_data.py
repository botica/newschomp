from types import SimpleNamespace
from datetime import datetime
import random

# Mock data for CSS development (used when settings.SKIP_CRAWL = True)
MOCK_ARTICLES = {
    'world': [
        SimpleNamespace(
            url='https://example.com/world-news-1',
            title='Global Summit Addresses Climate Change with New International Framework',
            pub_date=datetime(2024, 12, 18),
            content='Lorem ipsum dolor sit amet...',
            summary='World leaders agreed on binding emissions targets.\nThe framework includes a $100 billion green fund.\nImplementation begins in early 2025.',
            ai_title='Climate Summit Reaches Agreement',
            image_url='https://picsum.photos/seed/world1/800/600',
            topics=['Climate', 'Politics', 'International'],
            source='apnews'
        ),
        SimpleNamespace(
            url='https://example.com/world-news-2',
            title='Tech Giants Face New Regulations Across Multiple Continents',
            pub_date=datetime(2024, 12, 17),
            content='Lorem ipsum dolor sit amet...',
            summary='Major tech companies face sweeping new regulations.\nGovernments worldwide coordinate on antitrust efforts.\nData privacy rules will take effect next year.',
            ai_title='Tech Regulation Wave Grows',
            image_url='https://picsum.photos/seed/world2/800/600',
            topics=['Technology', 'Business', 'Regulation'],
            source='bbc'
        ),
    ],
    'color': [
        SimpleNamespace(
            url='https://example.com/local-news-1',
            title='New Mural Project Transforms Downtown District Into Open-Air Gallery',
            pub_date=datetime(2024, 12, 18),
            content='Lorem ipsum dolor sit amet...',
            summary='Artists completed murals across 12 downtown buildings.\nThe project creates a walkable outdoor gallery experience.\nFoot traffic to nearby businesses has increased significantly.',
            ai_title='Murals Transform Downtown District',
            image_url='https://picsum.photos/seed/color1/800/600',
            topics=['Art', 'Community', 'Urban Development'],
            source='urbanmilwaukee'
        ),
        SimpleNamespace(
            url='https://example.com/local-news-2',
            title='Historic Theater Reopens After Two-Year Restoration Project',
            pub_date=datetime(2024, 12, 17),
            content='Lorem ipsum dolor sit amet...',
            summary='The century-old venue reopens after extensive restoration.\nUpdates include modern acoustics and improved accessibility.\nOriginal architectural details have been carefully preserved.',
            ai_title='Historic Theater Reopens Today',
            image_url='https://picsum.photos/seed/color2/800/600',
            topics=['Culture', 'History', 'Entertainment'],
            source='gothamist'
        ),
    ],
}


def get_mock_article(category):
    """Return a random mock article for the given category."""
    articles = MOCK_ARTICLES.get(category, MOCK_ARTICLES['world'])
    return random.choice(articles)
