from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from .models import Article
from .forms import ArticleSearchForm
from .utils import generate_summary
from .sources import get_source
import requests


def home(request):
    articles = Article.objects.all()  # Uses model's default ordering: -created_at
    form = ArticleSearchForm()
    return render(request, 'chomp/home.html', {
        'articles': articles,
        'form': form
    })


def search_article(request):
    if request.method == 'POST':
        form = ArticleSearchForm(request.POST)
        if form.is_valid():
            query = form.cleaned_data['query']
            source_name = form.cleaned_data['source']

            try:
                # Get the news source
                source = get_source(source_name)
                if not source:
                    messages.error(request, 'News source not available.')
                    return redirect('home')

                # Search for articles (returns list of URLs sorted by relevance)
                article_urls = source.search(query)

                if not article_urls:
                    messages.error(request, 'No articles found for your search query.')
                    return redirect('home')

                # Iterate through URLs and find first non-duplicate
                article_added = False
                for article_url in article_urls:
                    # Check if this URL already exists in database
                    if Article.objects.filter(url=article_url).exists():
                        print(f"Skipping duplicate article: {article_url}")
                        continue

                    # This is a new article, fetch and extract it
                    print(f"Fetching new article: {article_url}")
                    html = source.fetch(article_url)

                    # Extract article data
                    article_data = source.extract(html)

                    if article_data and article_data.get('title') and article_data.get('url'):
                        # Generate AI summary
                        if article_data.get('content'):
                            ai_data = generate_summary(article_data['content'])
                            if ai_data:
                                article_data['summary'] = ai_data.get('summary')
                                article_data['ai_title'] = ai_data.get('ai_title')

                        # Create the article
                        article = Article.objects.create(
                            url=article_data['url'],
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
                messages.error(request, f'Error fetching article: {str(e)}')
                import traceback
                traceback.print_exc()

        else:
            messages.error(request, 'Please enter a valid search query.')

    return redirect('home')


def fetch_doorcountypulse(request):
    """
    Fetch a random article from Door County Pulse.
    This source doesn't use search queries - it picks from category pages.
    """
    if request.method == 'POST':
        try:
            # Get the Door County Pulse source
            source = get_source('doorcountypulse')
            if not source:
                messages.error(request, 'Door County Pulse source not available.')
                return redirect('home')

            # Get article URLs from a random category (no query needed)
            article_urls = source.search()

            if not article_urls:
                messages.error(request, 'No articles found on Door County Pulse.')
                return redirect('home')

            # Iterate through URLs and find first non-duplicate
            article_added = False
            for article_url in article_urls:
                # Check if this URL already exists in database
                if Article.objects.filter(url=article_url).exists():
                    print(f"Skipping duplicate article: {article_url}")
                    continue

                # This is a new article, fetch and extract it
                print(f"Fetching new article: {article_url}")
                html = source.fetch(article_url)

                # Extract article data
                article_data = source.extract(html)

                if article_data and article_data.get('title') and article_data.get('url'):
                    # Generate AI summary
                    if article_data.get('content'):
                        ai_data = generate_summary(article_data['content'])
                        if ai_data:
                            article_data['summary'] = ai_data.get('summary')
                            article_data['ai_title'] = ai_data.get('ai_title')

                    # Create the article
                    article = Article.objects.create(
                        url=article_data['url'],
                        title=article_data['title'],
                        pub_date=article_data.get('pub_date') or timezone.now(),
                        content=article_data.get('content', ''),
                        summary=article_data.get('summary', ''),
                        ai_title=article_data.get('ai_title', ''),
                        image_url=article_data.get('image_url', ''),
                        topics=article_data.get('topics', []),
                        source='doorcountypulse'
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
            messages.error(request, f'Error fetching Door County Pulse article: {str(e)}')
            import traceback
            traceback.print_exc()

    return redirect('home')


def fetch_urbanmilwaukee(request):
    """
    Fetch a random article from Urban Milwaukee.
    This source doesn't use search queries - it picks from category pages.
    """
    if request.method == 'POST':
        try:
            # Get the Urban Milwaukee source
            source = get_source('urbanmilwaukee')
            if not source:
                messages.error(request, 'Urban Milwaukee source not available.')
                return redirect('home')

            # Get article URLs from a random category (no query needed)
            article_urls = source.search()

            if not article_urls:
                messages.error(request, 'No articles found on Urban Milwaukee.')
                return redirect('home')

            # Iterate through URLs and find first non-duplicate
            article_added = False
            for article_url in article_urls:
                # Check if this URL already exists in database
                if Article.objects.filter(url=article_url).exists():
                    print(f"Skipping duplicate article: {article_url}")
                    continue

                # This is a new article, fetch and extract it
                print(f"Fetching new article: {article_url}")
                html = source.fetch(article_url)

                # Extract article data
                article_data = source.extract(html)

                if article_data and article_data.get('title') and article_data.get('url'):
                    # Generate AI summary
                    if article_data.get('content'):
                        ai_data = generate_summary(article_data['content'])
                        if ai_data:
                            article_data['summary'] = ai_data.get('summary')
                            article_data['ai_title'] = ai_data.get('ai_title')

                    # Create the article
                    article = Article.objects.create(
                        url=article_data['url'],
                        title=article_data['title'],
                        pub_date=article_data.get('pub_date') or timezone.now(),
                        content=article_data.get('content', ''),
                        summary=article_data.get('summary', ''),
                        ai_title=article_data.get('ai_title', ''),
                        image_url=article_data.get('image_url', ''),
                        topics=article_data.get('topics', []),
                        source='urbanmilwaukee'
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
            messages.error(request, f'Error fetching Urban Milwaukee article: {str(e)}')
            import traceback
            traceback.print_exc()

    return redirect('home')