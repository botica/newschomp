from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.csrf import ensure_csrf_cookie
from .models import Article
from .utils import generate_summary
from .sources import get_source
from urllib.parse import urlparse, urlunparse, unquote
import random


def normalize_url(url):
    """Normalize URL for duplicate checking: decode percent-encoding and strip fragment."""
    # First decode any percent-encoded characters (e.g., %E2%81%A0 -> actual unicode)
    decoded_url = unquote(url)
    # Then parse and strip fragment
    parsed = urlparse(decoded_url)
    return urlunparse(parsed._replace(fragment=''))


WORLD_SOURCES = ['apnews', 'bbc', 'reuters']
COLOR_SOURCES = ['austinchronicle', 'doorcountypulse', 'urbanmilwaukee',
                 'stlmag', 'blockclubchicago', 'gothamist', '303magazine',
                 'iexaminer', 'gambit', 'slugmag', 'folioweekly']


@ensure_csrf_cookie
def home(request):
    world_article = Article.objects.filter(source__in=WORLD_SOURCES).first()
    color_article = Article.objects.filter(source__in=COLOR_SOURCES).first()

    return render(request, 'chomp/home.html', {
        'world_article': world_article,
        'color_article': color_article,
    })


def fetch_article_from_source(request, source_name):
    """
    Fetch the first non-duplicate article from a news source's category page.
    """
    if request.method != 'POST':
        return redirect('home')

    try:
        # Get the news source
        source = get_source(source_name)
        if not source:
            messages.error(request, f'Source "{source_name}" not available.')
            return redirect('home')

        # Get article URLs from source (either via search or category/RSS)
        article_urls = source.search()

        if not article_urls:
            messages.error(request, f'No articles found from {source.name}.')
            return redirect('home')

        # Iterate through URLs and find first non-duplicate
        article_added = False
        for article_url in article_urls:
            # Check if this URL already exists in database (normalize to strip fragments)
            normalized_url = normalize_url(article_url)
            if Article.objects.filter(url=normalized_url).exists():
                print(f"Skipping duplicate article: {article_url}")
                continue

            # This is a new article, fetch and extract it
            print(f"Fetching new article: {article_url}")
            html = source.fetch(article_url)

            # Extract article data
            article_data = source.extract(html)

            if article_data and article_data.get('title') and article_data.get('url'):
                # Check if the canonical URL (from page) is also a duplicate
                # This handles cases where search URL differs from canonical URL
                canonical_url = normalize_url(article_data['url'])
                if Article.objects.filter(url=canonical_url).exists():
                    print(f"Skipping duplicate article (canonical URL): {canonical_url}")
                    continue

                # Generate AI summary if content is available
                if article_data.get('content'):
                    ai_data = generate_summary(article_data['content'])
                    if ai_data:
                        article_data['summary'] = ai_data.get('summary')
                        article_data['ai_title'] = ai_data.get('ai_title')

                # Create the article with normalized URL for consistent duplicate checking
                article = Article.objects.create(
                    url=normalize_url(article_data['url']),
                    title=article_data['title'],
                    pub_date=article_data.get('pub_date') or timezone.now(),
                    content=article_data.get('content', ''),
                    summary=article_data.get('summary', ''),
                    ai_title=article_data.get('ai_title', ''),
                    image_url=article_data.get('image_url', ''),
                    topics=article_data.get('topics', []),
                    source=source_name
                )

                messages.success(request, f'Article "{article.ai_title or article.title}" added successfully!')
                article_added = True
                break
            else:
                print(f"Failed to extract data from: {article_url}")
                continue

        if not article_added:
            messages.warning(request, 'All articles found were already in the database.')

    except Exception as e:
        messages.error(request, f'Error fetching article from {source_name}: {str(e)}')
        import traceback
        traceback.print_exc()

    return redirect('home')


def refresh_article(request, category):
    """
    Fetch a new article from a source in the specified category.
    Returns JSON with the rendered HTML for the article.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    try:
        # Determine which sources to use based on category
        if category == 'world':
            sources_to_try = WORLD_SOURCES.copy()
        elif category == 'color':
            sources_to_try = COLOR_SOURCES.copy()
        else:
            return JsonResponse({'success': False, 'error': 'Invalid category'})

        # Shuffle to randomly pick which source to try first
        random.shuffle(sources_to_try)

        article_created = None
        for source_name in sources_to_try:
            source = get_source(source_name)

            if not source:
                print(f'Source "{source_name}" not available, trying next...')
                continue

            # Get article URLs from source
            article_urls = source.search()

            if not article_urls:
                print(f'No articles found from {source.name}, trying next source...')
                continue

            # Iterate through URLs and find first non-duplicate
            for article_url in article_urls:
                # Check if this URL already exists in database
                normalized_url = normalize_url(article_url)
                if Article.objects.filter(url=normalized_url).exists():
                    print(f"Skipping duplicate article: {article_url}")
                    continue

                # This is a new article, fetch and extract it
                print(f"Fetching new article: {article_url}")
                html = source.fetch(article_url)

                # Extract article data
                article_data = source.extract(html)

                if article_data and article_data.get('title') and article_data.get('url'):
                    # Check if the canonical URL (from page) is also a duplicate
                    # This handles cases where search URL differs from canonical URL
                    canonical_url = normalize_url(article_data['url'])
                    if Article.objects.filter(url=canonical_url).exists():
                        print(f"Skipping duplicate article (canonical URL): {canonical_url}")
                        continue

                    # Generate AI summary if content is available
                    if article_data.get('content'):
                        ai_data = generate_summary(article_data['content'])
                        if ai_data:
                            article_data['summary'] = ai_data.get('summary')
                            article_data['ai_title'] = ai_data.get('ai_title')

                    # Create the article
                    article_created = Article.objects.create(
                        url=normalize_url(article_data['url']),
                        title=article_data['title'],
                        pub_date=article_data.get('pub_date') or timezone.now(),
                        content=article_data.get('content', ''),
                        summary=article_data.get('summary', ''),
                        ai_title=article_data.get('ai_title', ''),
                        image_url=article_data.get('image_url', ''),
                        topics=article_data.get('topics', []),
                        source=source_name
                    )
                    break
                else:
                    print(f"Failed to extract data from: {article_url}")
                    continue

            # If we created an article, break out of the source loop
            if article_created:
                break
            else:
                print(f"All articles from {source_name} were duplicates, trying next source...")

        if not article_created:
            return JsonResponse({'success': False, 'error': 'All sources exhausted - no new articles found'})

        # Render the article HTML
        context_key = f'{category}_article'
        html_content = render_to_string('chomp/article_partial.html', {
            'article': article_created,
            'category': category
        })

        return JsonResponse({
            'success': True,
            'html': html_content
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)})