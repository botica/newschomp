from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from .models import Article
from .forms import ArticleSearchForm
from .utils import search_and_extract_article


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

            try:
                # Search and extract article data
                article_data = search_and_extract_article(query)

                if article_data and article_data.get('title') and article_data.get('url'):
                    # Create or update Article object
                    article, created = Article.objects.update_or_create(
                        url=article_data['url'],
                        defaults={
                            'title': article_data['title'],
                            'pub_date': article_data.get('pub_date') or timezone.now(),
                            'content': article_data.get('content', ''),
                            'summary': article_data.get('summary', article_data.get('title', '')),
                            'ai_title': article_data.get('ai_title', '')
                        }
                    )

                    if created:
                        messages.success(request, f'Article "{article.title}" added successfully with AI summary!')
                    else:
                        messages.success(request, f'Article "{article.title}" updated with new AI summary!')
                else:
                    messages.error(request, 'No article found for your search query.')

            except Exception as e:
                messages.error(request, f'Error fetching article: {str(e)}')

        else:
            messages.error(request, 'Please enter a valid search query.')

    return redirect('home')