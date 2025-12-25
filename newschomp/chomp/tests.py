"""
Core test suite for the chomp app.

12 essential tests covering:
- URL normalization for deduplication
- Session-based URL tracking
- LLM integration (mocked)
- News source detection and extraction
- Geolocation
- Django views
- Article model
- Full fetch pipeline
"""
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from unittest.mock import patch, MagicMock
import json

from .models import Article
from .views import normalize_url, get_seen_urls, mark_url_seen, fetch_article_from_sources
from .sources import get_source, get_source_for_url, find_nearest_source


class NormalizeUrlTests(TestCase):
    """Test URL normalization for duplicate detection."""

    def test_combined_fragment_and_encoding(self):
        """Both fragment and percent-encoding should be handled."""
        url = "https://example.com/article%2F123#section"
        expected = "https://example.com/article/123"
        self.assertEqual(normalize_url(url), expected)


class SessionUrlTrackingTests(TestCase):
    """Test session-based URL deduplication."""

    def test_mark_url_seen_100_limit(self):
        """Should maintain 100 URL limit per category (FIFO eviction)."""
        request = MagicMock()
        existing_urls = [f'https://example.com/{i}' for i in range(100)]
        request.session = {'seen_urls': {'world': existing_urls.copy()}}

        mark_url_seen(request, 'https://example.com/new', 'world')

        self.assertEqual(len(request.session['seen_urls']['world']), 100)
        self.assertNotIn('https://example.com/0', request.session['seen_urls']['world'])
        self.assertIn('https://example.com/new', request.session['seen_urls']['world'])


class GenerateSummaryTests(TestCase):
    """Test LLM summary generation with mocked OpenAI API."""

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_successful_summary_generation(self, mock_openai):
        """Should parse LLM response correctly."""
        from .utils import generate_summary

        mock_response = MagicMock()
        mock_response.output_text = """TITLE: Breaking News Today
First summary line about the event.
Second line with more details.
Third line concluding the summary."""

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        result = generate_summary("Article content here...")

        self.assertIsNotNone(result)
        self.assertEqual(result['ai_title'], 'Breaking News Today')
        self.assertIn('First summary line', result['summary'])

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_handles_api_error(self, mock_openai):
        """Should return None on API error (graceful degradation)."""
        from .utils import generate_summary

        mock_client = MagicMock()
        mock_client.responses.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        result = generate_summary("Article content")
        self.assertIsNone(result)


class SourceTests(TestCase):
    """Test source factory and URL detection."""

    def test_get_valid_source(self):
        """Should return source instance for valid name."""
        source = get_source('apnews')
        self.assertIsNotNone(source)
        self.assertEqual(source.name, "AP News")
        self.assertEqual(source.source_key, "apnews")

    def test_url_to_source_detection(self):
        """Should detect correct source from article URL."""
        source = get_source_for_url("https://apnews.com/article/123")
        self.assertIsNotNone(source)
        self.assertEqual(source.source_key, "apnews")


class APNewsExtractionTests(TestCase):
    """Test article extraction from HTML."""

    @patch('chomp.utils.extract_topics_with_llm', return_value=['Politics', 'World'])
    def test_extract_basic_article(self, mock_topics):
        """Should extract article data from AP News HTML."""
        source = get_source('apnews')

        html = '''
        <html>
        <head>
            <meta property="og:title" content="Test Article Title">
            <meta property="og:url" content="https://apnews.com/article/test-123">
            <meta property="article:published_time" content="2024-01-15T10:30:00Z">
        </head>
        <body>
            <div class="Page-content">
                <picture>
                    <img class="Image" src="https://example.com/image.jpg">
                </picture>
            </div>
            <div class="RichTextStoryBody RichTextBody">
                This is the article content. It contains important information.
            </div>
        </body>
        </html>
        '''

        result = source.extract(html)

        self.assertEqual(result['title'], 'Test Article Title')
        self.assertEqual(result['url'], 'https://apnews.com/article/test-123')
        self.assertIn('article content', result['content'])
        self.assertEqual(result['image_url'], 'https://example.com/image.jpg')


class GeolocationTests(TestCase):
    """Test geolocation and nearest source finding."""

    def test_find_nearest_source(self):
        """Should find Austin Chronicle as nearest for Austin coordinates."""
        result = find_nearest_source(30.2672, -97.7431)
        self.assertIsNotNone(result)
        self.assertEqual(result['source_key'], 'austinchronicle')
        self.assertIn('distance_km', result)


class ViewTests(TestCase):
    """Test Django view endpoints."""

    def test_home_returns_200(self):
        """Home page should return 200 OK."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'chomp/home.html')

    @override_settings(SKIP_CRAWL=True)
    def test_refresh_returns_article(self):
        """Refresh endpoint should return article data."""
        response = self.client.post('/refresh/world/')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('html', data)


class ArticleModelTests(TestCase):
    """Test Article model."""

    def test_create_article(self):
        """Should create article with required fields."""
        article = Article.objects.create(
            title="Test Article",
            pub_date=timezone.now(),
            url="https://example.com/article"
        )
        self.assertEqual(article.title, "Test Article")
        self.assertIsNotNone(article.created_at)
        self.assertEqual(str(article), "Test Article")


class FetchArticlePipelineTests(TestCase):
    """Test the article fetching pipeline end-to-end."""

    @patch('chomp.views.get_source')
    def test_skips_seen_urls(self, mock_get_source):
        """Should skip URLs already in seen list (core dedup feature)."""
        mock_source = MagicMock()
        mock_source.search.return_value = ['https://example.com/seen-article']
        mock_get_source.return_value = mock_source

        seen_urls = ['https://example.com/seen-article']
        result = fetch_article_from_sources(['testsource'], seen_urls)

        self.assertIsNone(result)
        mock_source.fetch.assert_not_called()

    @patch('chomp.views.get_source')
    @patch('chomp.views.generate_summary')
    def test_returns_article_with_summary(self, mock_summary, mock_get_source):
        """Should return article with generated summary (full pipeline)."""
        mock_source = MagicMock()
        mock_source.search.return_value = ['https://example.com/article']
        mock_source.fetch.return_value = '<html></html>'
        mock_source.extract.return_value = {
            'title': 'Test Article',
            'url': 'https://example.com/article',
            'content': 'Article content here',
            'pub_date': None,
            'image_url': None,
            'topics': ['Test']
        }
        mock_get_source.return_value = mock_source

        mock_summary.return_value = {
            'ai_title': 'AI Generated Title',
            'summary': 'AI generated summary.'
        }

        result = fetch_article_from_sources(['testsource'], [])

        self.assertIsNotNone(result)
        self.assertEqual(result.title, 'Test Article')
        self.assertEqual(result.ai_title, 'AI Generated Title')
        self.assertEqual(result.summary, 'AI generated summary.')
