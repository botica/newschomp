from django.shortcuts import render
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings
from .utils import generate_summary, LLM_MODEL
from .sources import get_source, find_nearest_source, get_source_for_url
from .mock_data import get_mock_article
from urllib.parse import urlparse, urlunparse, unquote
from types import SimpleNamespace
import random


def normalize_url(url):
    """Normalize URL for duplicate checking: decode percent-encoding and strip fragment."""
    decoded_url = unquote(url)
    parsed = urlparse(decoded_url)
    return urlunparse(parsed._replace(fragment=''))


def get_seen_urls(request, category):
    """Get list of seen normalized URLs for a category from session."""
    seen = request.session.get('seen_urls', {})
    return seen.get(category, [])


def mark_url_seen(request, url, category):
    """Add normalized URL to seen list in session, maintaining 100 item limit."""
    if url is None:
        return
    normalized = normalize_url(url)
    seen = request.session.get('seen_urls', {})
    category_seen = seen.get(category, [])

    if normalized not in category_seen:
        category_seen.append(normalized)
        if len(category_seen) > 100:
            category_seen = category_seen[-100:]
        seen[category] = category_seen
        request.session['seen_urls'] = seen


def fetch_article_from_sources(sources, seen_urls):
    """
    Crawl sources and return first unseen article as a SimpleNamespace.
    Returns None if no unseen articles found.
    """
    random.shuffle(sources)

    for source_name in sources:
        source = get_source(source_name)
        if not source:
            continue

        article_urls = source.search()
        if not article_urls:
            continue

        for article_url in article_urls:
            normalized_url = normalize_url(article_url)

            # Skip if user has already seen this URL
            if normalized_url in seen_urls:
                print(f"Skipping already-seen article: {article_url}")
                continue

            # Fetch and extract
            print(f"Fetching article: {article_url}")
            html = source.fetch(article_url)
            article_data = source.extract(html)

            if article_data and article_data.get('title') and article_data.get('url'):
                canonical_url = normalize_url(article_data['url'])
                if canonical_url in seen_urls:
                    continue

                # Generate fresh summary
                summary = ''
                ai_title = ''
                if article_data.get('content'):
                    ai_data = generate_summary(article_data['content'])
                    if ai_data:
                        summary = ai_data.get('summary', '')
                        ai_title = ai_data.get('ai_title', '')

                # Return as SimpleNamespace (works like an object in templates)
                return SimpleNamespace(
                    url=canonical_url,
                    title=article_data['title'],
                    pub_date=article_data.get('pub_date'),
                    content=article_data.get('content', ''),
                    summary=summary,
                    ai_title=ai_title,
                    image_url=article_data.get('image_url', ''),
                    topics=article_data.get('topics', []),
                    source=source_name
                )

    return None


WORLD_SOURCES = ['apnews', 'bbc', 'reuters']
COLOR_SOURCES = ['austinchronicle', 'doorcountypulse', 'urbanmilwaukee',
                 'stlmag', 'blockclubchicago', 'gothamist', '303magazine',
                 'iexaminer', 'gambit', 'slugmag', 'folioweekly']


@ensure_csrf_cookie
def home(request):
    # Return empty - articles will be loaded asynchronously via JS
    return render(request, 'chomp/home.html', {
        'world_article': None,
        'color_article': None,
        'llm_model': LLM_MODEL,
    })


def refresh_article(request, category):
    """Fetch a new article for the specified category."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    try:
        if category not in ('world', 'color'):
            return JsonResponse({'success': False, 'error': 'Invalid category'})

        # Skip crawling and return mock data for CSS development
        if getattr(settings, 'SKIP_CRAWL', False):
            article = get_mock_article(category)
        else:
            if category == 'world':
                sources = WORLD_SOURCES.copy()
            else:
                sources = COLOR_SOURCES.copy()

            seen_urls = get_seen_urls(request, category)
            article = fetch_article_from_sources(sources, seen_urls)

        if not article:
            return JsonResponse({'success': False, 'error': 'No new articles found'})

        mark_url_seen(request, article.url, category)

        html_content = render_to_string('chomp/article_partial.html', {
            'article': article,
            'category': category,
            'llm_model': LLM_MODEL,
        })

        return JsonResponse({'success': True, 'html': html_content})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})


def get_nearest_source(request):
    """Find the nearest local news source based on user's location."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    try:
        import json
        data = json.loads(request.body)
        user_lat = float(data.get('latitude'))
        user_lng = float(data.get('longitude'))

        nearest = find_nearest_source(user_lat, user_lng)

        if nearest:
            return JsonResponse({'success': True, 'source': nearest})
        else:
            return JsonResponse({'success': False, 'error': 'No local sources available'})

    except (json.JSONDecodeError, TypeError, ValueError) as e:
        return JsonResponse({'success': False, 'error': f'Invalid location data: {str(e)}'})


def fetch_from_source(request, source_name):
    """Fetch a new article from a specific source."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    try:
        source = get_source(source_name)
        if not source:
            return JsonResponse({'success': False, 'error': f'Source "{source_name}" not available'})

        # Skip crawling and return mock data for CSS development
        if getattr(settings, 'SKIP_CRAWL', False):
            article = get_mock_article('color')
        else:
            seen_urls = get_seen_urls(request, 'color')
            article = fetch_article_from_sources([source_name], seen_urls)

        if not article:
            return JsonResponse({'success': False, 'error': f'No new articles from {source.name}'})

        mark_url_seen(request, article.url, 'color')

        html_content = render_to_string('chomp/article_partial.html', {
            'article': article,
            'category': 'color',
            'llm_model': LLM_MODEL,
        })

        return JsonResponse({
            'success': True,
            'html': html_content,
            'source_name': source.name,
            'source_city': source.city
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})


def test_url(request):
    """Fetch and display a specific article URL for testing."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    try:
        import json
        data = json.loads(request.body)
        url = data.get('url', '').strip()

        if not url:
            return JsonResponse({'success': False, 'error': 'URL is required'})

        # Detect source from URL
        source = get_source_for_url(url)
        if not source:
            return JsonResponse({'success': False, 'error': f'No source found for URL: {url}'})

        # Fetch and extract
        print(f"Test URL: Fetching {url} using {source.name}")
        html = source.fetch(url)
        article_data = source.extract(html)

        if not article_data or not article_data.get('title'):
            return JsonResponse({'success': False, 'error': 'Failed to extract article data'})

        # Generate summary
        summary = ''
        ai_title = ''
        if article_data.get('content'):
            ai_data = generate_summary(article_data['content'])
            if ai_data:
                summary = ai_data.get('summary', '')
                ai_title = ai_data.get('ai_title', '')

        # Build article object
        article = SimpleNamespace(
            url=article_data.get('url') or url,
            title=article_data['title'],
            pub_date=article_data.get('pub_date'),
            content=article_data.get('content', ''),
            summary=summary,
            ai_title=ai_title,
            image_url=article_data.get('image_url', ''),
            topics=article_data.get('topics', []),
            source=source.source_key
        )

        # Determine category based on source
        if source.source_key in WORLD_SOURCES:
            category = 'world'
        else:
            category = 'color'

        html_content = render_to_string('chomp/article_partial.html', {
            'article': article,
            'category': category,
            'llm_model': LLM_MODEL,
        })

        return JsonResponse({
            'success': True,
            'html': html_content,
            'source_name': source.name,
            'category': category
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})
