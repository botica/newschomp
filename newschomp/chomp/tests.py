"""
Comprehensive test suite for the chomp app.

Test categories:
1. URL normalization and deduplication
2. LLM integration (mocked)
3. News source extraction
4. Geolocation/nearest source
5. Django views/endpoints
6. Model tests
"""
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from unittest.mock import patch, MagicMock
import json

from .models import Article
from .views import normalize_url, get_seen_urls, mark_url_seen, fetch_article_from_sources
from .sources import get_source, get_source_for_url, find_nearest_source, get_local_sources_with_locations
from .utils import generate_summary, extract_topics_with_llm


# =============================================================================
# URL NORMALIZATION TESTS
# =============================================================================

class NormalizeUrlTests(TestCase):
    """Test URL normalization for duplicate detection."""

    def test_basic_url_unchanged(self):
        """Basic URLs without special characters should remain unchanged."""
        url = "https://example.com/article/123"
        self.assertEqual(normalize_url(url), url)

    def test_strips_fragment(self):
        """URL fragments (#anchor) should be stripped."""
        url = "https://example.com/article#comments"
        expected = "https://example.com/article"
        self.assertEqual(normalize_url(url), expected)

    def test_decodes_percent_encoding(self):
        """Percent-encoded characters should be decoded."""
        url = "https://example.com/article%2F123"
        expected = "https://example.com/article/123"
        self.assertEqual(normalize_url(url), expected)

    def test_decodes_spaces(self):
        """Encoded spaces (%20) should be decoded."""
        url = "https://example.com/article%20title"
        expected = "https://example.com/article title"
        self.assertEqual(normalize_url(url), expected)

    def test_handles_complex_encoding(self):
        """Complex percent-encoded URLs should be fully decoded."""
        url = "https://example.com/%E2%9C%93check"  # ✓ encoded
        expected = "https://example.com/✓check"
        self.assertEqual(normalize_url(url), expected)

    def test_combined_fragment_and_encoding(self):
        """Both fragment and encoding should be handled."""
        url = "https://example.com/article%2F123#section"
        expected = "https://example.com/article/123"
        self.assertEqual(normalize_url(url), expected)

    def test_preserves_query_params(self):
        """Query parameters should be preserved."""
        url = "https://example.com/article?id=123&source=home"
        self.assertEqual(normalize_url(url), url)


# =============================================================================
# SESSION URL TRACKING TESTS
# =============================================================================

class SessionUrlTrackingTests(TestCase):
    """Test session-based URL deduplication."""

    def setUp(self):
        self.client = Client()

    def test_get_seen_urls_empty_session(self):
        """Empty session should return empty list."""
        request = MagicMock()
        request.session = {}
        result = get_seen_urls(request, 'world')
        self.assertEqual(result, [])

    def test_get_seen_urls_with_data(self):
        """Should return URLs for the specified category."""
        request = MagicMock()
        request.session = {
            'seen_urls': {
                'world': ['https://example.com/1', 'https://example.com/2'],
                'color': ['https://local.com/1']
            }
        }
        result = get_seen_urls(request, 'world')
        self.assertEqual(result, ['https://example.com/1', 'https://example.com/2'])

    def test_get_seen_urls_wrong_category(self):
        """Should return empty list for non-existent category."""
        request = MagicMock()
        request.session = {'seen_urls': {'world': ['https://example.com/1']}}
        result = get_seen_urls(request, 'color')
        self.assertEqual(result, [])

    def test_mark_url_seen_adds_url(self):
        """Should add normalized URL to session."""
        request = MagicMock()
        request.session = {}
        mark_url_seen(request, 'https://example.com/article#section', 'world')
        self.assertIn('https://example.com/article', request.session['seen_urls']['world'])

    def test_mark_url_seen_none_url(self):
        """Should handle None URL gracefully."""
        request = MagicMock()
        request.session = {}
        mark_url_seen(request, None, 'world')
        self.assertEqual(request.session, {})

    def test_mark_url_seen_no_duplicates(self):
        """Should not add duplicate URLs."""
        request = MagicMock()
        request.session = {'seen_urls': {'world': ['https://example.com/article']}}
        mark_url_seen(request, 'https://example.com/article', 'world')
        self.assertEqual(len(request.session['seen_urls']['world']), 1)

    def test_mark_url_seen_100_limit(self):
        """Should maintain 100 URL limit per category."""
        request = MagicMock()
        # Pre-populate with 100 URLs
        existing_urls = [f'https://example.com/{i}' for i in range(100)]
        request.session = {'seen_urls': {'world': existing_urls.copy()}}

        # Add one more
        mark_url_seen(request, 'https://example.com/new', 'world')

        # Should still have 100 URLs
        self.assertEqual(len(request.session['seen_urls']['world']), 100)
        # First URL should be removed, new one should be present
        self.assertNotIn('https://example.com/0', request.session['seen_urls']['world'])
        self.assertIn('https://example.com/new', request.session['seen_urls']['world'])


# =============================================================================
# LLM INTEGRATION TESTS (MOCKED)
# =============================================================================

class GenerateSummaryTests(TestCase):
    """Test LLM summary generation with mocked OpenAI API."""

    @patch.dict('os.environ', {'OPENAI_API_KEY': ''})
    def test_no_api_key_returns_none(self):
        """Should return None when API key is missing."""
        result = generate_summary("Some article content")
        self.assertIsNone(result)

    def test_empty_content_returns_none(self):
        """Should return None for empty content."""
        result = generate_summary("")
        self.assertIsNone(result)

    def test_none_content_returns_none(self):
        """Should return None for None content."""
        result = generate_summary(None)
        self.assertIsNone(result)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_successful_summary_generation(self, mock_openai):
        """Should parse LLM response correctly."""
        # Mock the OpenAI response
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
        self.assertIn('Second line', result['summary'])
        self.assertIn('Third line', result['summary'])

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_truncates_long_content(self, mock_openai):
        """Should truncate content to 4000 characters."""
        mock_response = MagicMock()
        mock_response.output_text = "TITLE: Test Title\nSummary line."

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        # Create content longer than 4000 chars
        long_content = "x" * 5000
        generate_summary(long_content)

        # Verify the content sent to API was truncated
        call_args = mock_client.responses.create.call_args
        input_messages = call_args.kwargs['input']
        user_message = input_messages[1]['content']
        # The content in the message should be truncated
        self.assertLessEqual(len(user_message), 4000 + len("Summarize this article:\n\n"))

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_handles_api_error(self, mock_openai):
        """Should return None on API error."""
        mock_client = MagicMock()
        mock_client.responses.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        result = generate_summary("Article content")
        self.assertIsNone(result)


class ExtractTopicsTests(TestCase):
    """Test LLM topic extraction with mocked OpenAI API."""

    @patch.dict('os.environ', {'OPENAI_API_KEY': ''})
    def test_no_api_key_returns_empty(self):
        """Should return empty list when API key is missing."""
        result = extract_topics_with_llm("Some article content")
        self.assertEqual(result, [])

    def test_empty_content_returns_empty(self):
        """Should return empty list for empty content."""
        result = extract_topics_with_llm("")
        self.assertEqual(result, [])

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_successful_topic_extraction(self, mock_openai):
        """Should parse topic response correctly."""
        mock_response = MagicMock()
        mock_response.output_text = """Politics
Technology
Climate"""

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        result = extract_topics_with_llm("Article about politics and tech...")

        self.assertEqual(len(result), 3)
        self.assertIn('Politics', result)
        self.assertIn('Technology', result)
        self.assertIn('Climate', result)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_handles_api_error(self, mock_openai):
        """Should return empty list on API error."""
        mock_client = MagicMock()
        mock_client.responses.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        result = extract_topics_with_llm("Article content")
        self.assertEqual(result, [])


# =============================================================================
# NEWS SOURCE TESTS
# =============================================================================

class GetSourceTests(TestCase):
    """Test source factory function."""

    def test_get_valid_source(self):
        """Should return source instance for valid name."""
        source = get_source('apnews')
        self.assertIsNotNone(source)
        self.assertEqual(source.name, "AP News")
        self.assertEqual(source.source_key, "apnews")

    def test_get_invalid_source(self):
        """Should return None for invalid source name."""
        source = get_source('nonexistent')
        self.assertIsNone(source)

    def test_get_source_case_insensitive(self):
        """Should handle case-insensitive source names."""
        source = get_source('APNEWS')
        self.assertIsNotNone(source)
        self.assertEqual(source.source_key, "apnews")

    def test_all_registered_sources(self):
        """All registered sources should be instantiable."""
        source_names = [
            'apnews', 'bbc', 'reuters', 'austinchronicle', 'doorcountypulse',
            'urbanmilwaukee', 'stlmag', 'blockclubchicago', 'gothamist',
            '303magazine', 'iexaminer', 'gambit', 'slugmag', 'folioweekly'
        ]
        for name in source_names:
            source = get_source(name)
            self.assertIsNotNone(source, f"Source '{name}' should be available")


class GetSourceForUrlTests(TestCase):
    """Test URL-to-source mapping."""

    def test_apnews_url(self):
        """Should detect AP News URLs."""
        source = get_source_for_url("https://apnews.com/article/123")
        self.assertIsNotNone(source)
        self.assertEqual(source.source_key, "apnews")

    def test_apnews_www_url(self):
        """Should detect AP News URLs with www."""
        source = get_source_for_url("https://www.apnews.com/article/123")
        self.assertIsNotNone(source)
        self.assertEqual(source.source_key, "apnews")

    def test_bbc_url(self):
        """Should detect BBC URLs."""
        source = get_source_for_url("https://www.bbc.com/news/world-123")
        self.assertIsNotNone(source)
        self.assertEqual(source.source_key, "bbc")

    def test_bbc_co_uk_url(self):
        """Should detect BBC .co.uk URLs."""
        source = get_source_for_url("https://www.bbc.co.uk/news/article")
        self.assertIsNotNone(source)
        self.assertEqual(source.source_key, "bbc")

    def test_reuters_url(self):
        """Should detect Reuters URLs."""
        source = get_source_for_url("https://www.reuters.com/world/article")
        self.assertIsNotNone(source)
        self.assertEqual(source.source_key, "reuters")

    def test_local_source_url(self):
        """Should detect local source URLs."""
        source = get_source_for_url("https://www.austinchronicle.com/news/article")
        self.assertIsNotNone(source)
        self.assertEqual(source.source_key, "austinchronicle")

    def test_unknown_domain(self):
        """Should return None for unknown domains."""
        source = get_source_for_url("https://www.unknownnews.com/article")
        self.assertIsNone(source)


class APNewsExtractionTests(TestCase):
    """Test AP News HTML extraction."""

    @patch('chomp.utils.extract_topics_with_llm', return_value=['Politics', 'World'])
    def test_extract_basic_article(self, mock_topics):
        """Should extract article data from AP News HTML."""
        source = get_source('apnews')

        # Mock HTML with AP News structure
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
        self.assertIsNotNone(result['pub_date'])
        self.assertIn('article content', result['content'])
        self.assertEqual(result['image_url'], 'https://example.com/image.jpg')
        self.assertEqual(result['topics'], ['Politics', 'World'])

    def test_extract_missing_optional_fields(self):
        """Should handle missing optional fields gracefully."""
        source = get_source('apnews')

        html = '''
        <html>
        <head>
            <meta property="og:title" content="Test Title">
            <meta property="og:url" content="https://apnews.com/article/test">
        </head>
        <body></body>
        </html>
        '''

        # No content means extract_topics_with_llm won't be called
        result = source.extract(html)

        self.assertEqual(result['title'], 'Test Title')
        self.assertIsNone(result['content'])
        self.assertIsNone(result['image_url'])
        self.assertEqual(result['topics'], [])  # Empty because no content

    @patch('chomp.utils.extract_topics_with_llm', return_value=[])
    def test_extract_video_player_poster(self, mock_topics):
        """Should extract poster from video player."""
        source = get_source('apnews')

        html = '''
        <html>
        <head>
            <meta property="og:title" content="Video Article">
            <meta property="og:url" content="https://apnews.com/article/video">
        </head>
        <body>
            <div class="Page-content">
                <bsp-jw-player poster="https://example.com/video-poster.jpg"></bsp-jw-player>
                <picture>
                    <img class="Image" src="https://example.com/fallback.jpg">
                </picture>
            </div>
        </body>
        </html>
        '''

        result = source.extract(html)

        # Video poster should take priority over picture
        self.assertEqual(result['image_url'], 'https://example.com/video-poster.jpg')


# =============================================================================
# GEOLOCATION TESTS
# =============================================================================

class GeolocationTests(TestCase):
    """Test geolocation and nearest source finding."""

    def test_find_nearest_source_austin(self):
        """Should find Austin Chronicle as nearest for Austin coordinates."""
        # Austin, TX coordinates
        result = find_nearest_source(30.2672, -97.7431)
        self.assertIsNotNone(result)
        self.assertEqual(result['source_key'], 'austinchronicle')
        self.assertIn('distance_km', result)

    def test_find_nearest_source_chicago(self):
        """Should find Block Club Chicago as nearest for Chicago coordinates."""
        # Chicago, IL coordinates
        result = find_nearest_source(41.8781, -87.6298)
        self.assertIsNotNone(result)
        self.assertEqual(result['source_key'], 'blockclubchicago')

    def test_find_nearest_source_nyc(self):
        """Should find Gothamist as nearest for NYC coordinates."""
        # New York City coordinates
        result = find_nearest_source(40.7128, -74.0060)
        self.assertIsNotNone(result)
        self.assertEqual(result['source_key'], 'gothamist')

    def test_find_nearest_source_milwaukee(self):
        """Should find Urban Milwaukee as nearest for Milwaukee coordinates."""
        # Milwaukee, WI coordinates
        result = find_nearest_source(43.0389, -87.9065)
        self.assertIsNotNone(result)
        self.assertEqual(result['source_key'], 'urbanmilwaukee')

    def test_distance_calculation_sanity(self):
        """Distance should be reasonable for nearby location."""
        # Very close to Austin
        result = find_nearest_source(30.27, -97.74)
        self.assertLess(result['distance_km'], 5)  # Should be within 5km

    def test_get_local_sources_with_locations(self):
        """Should return all local sources with location data."""
        sources = get_local_sources_with_locations()
        self.assertGreater(len(sources), 0)

        for source in sources:
            self.assertIn('source_key', source)
            self.assertIn('name', source)
            self.assertIn('latitude', source)
            self.assertIn('longitude', source)
            self.assertIsNotNone(source['latitude'])
            self.assertIsNotNone(source['longitude'])


# =============================================================================
# DJANGO VIEW TESTS
# =============================================================================

class HomeViewTests(TestCase):
    """Test home page view."""

    def test_home_returns_200(self):
        """Home page should return 200 OK."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_home_uses_correct_template(self):
        """Home page should use the correct template."""
        response = self.client.get('/')
        self.assertTemplateUsed(response, 'chomp/home.html')

    def test_home_sets_csrf_cookie(self):
        """Home page should set CSRF cookie."""
        response = self.client.get('/')
        self.assertIn('csrftoken', response.cookies)


class RefreshArticleViewTests(TestCase):
    """Test article refresh endpoint."""

    def test_get_request_rejected(self):
        """GET requests should be rejected."""
        response = self.client.get('/refresh/world/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Invalid request method', data['error'])

    def test_invalid_category(self):
        """Invalid category should return error."""
        response = self.client.post('/refresh/invalid/')
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Invalid category', data['error'])

    @override_settings(SKIP_CRAWL=True)
    def test_skip_crawl_returns_mock(self):
        """With SKIP_CRAWL=True, should return mock article."""
        response = self.client.post('/refresh/world/')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('html', data)

    @override_settings(SKIP_CRAWL=True)
    def test_color_category_works(self):
        """Color category should work with mock data."""
        response = self.client.post('/refresh/color/')
        data = response.json()
        self.assertTrue(data['success'])


class NearestSourceViewTests(TestCase):
    """Test nearest source endpoint."""

    def test_get_request_rejected(self):
        """GET requests should be rejected."""
        response = self.client.get('/nearest-source/')
        data = response.json()
        self.assertFalse(data['success'])

    def test_valid_location(self):
        """Valid location should return nearest source."""
        response = self.client.post(
            '/nearest-source/',
            data=json.dumps({'latitude': 30.2672, 'longitude': -97.7431}),
            content_type='application/json'
        )
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('source', data)
        self.assertIn('source_key', data['source'])

    def test_invalid_json(self):
        """Invalid JSON should return error."""
        response = self.client.post(
            '/nearest-source/',
            data='not json',
            content_type='application/json'
        )
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('Invalid location data', data['error'])

    def test_missing_latitude(self):
        """Missing latitude should return error."""
        response = self.client.post(
            '/nearest-source/',
            data=json.dumps({'longitude': -97.7431}),
            content_type='application/json'
        )
        data = response.json()
        self.assertFalse(data['success'])


class FetchFromSourceViewTests(TestCase):
    """Test fetch from specific source endpoint."""

    def test_get_request_rejected(self):
        """GET requests should be rejected."""
        response = self.client.get('/fetch-local/apnews/')
        data = response.json()
        self.assertFalse(data['success'])

    def test_invalid_source(self):
        """Invalid source should return error."""
        response = self.client.post('/fetch-local/nonexistent/')
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('not available', data['error'])

    @override_settings(SKIP_CRAWL=True)
    def test_valid_source_with_mock(self):
        """Valid source with SKIP_CRAWL should return mock."""
        response = self.client.post('/fetch-local/austinchronicle/')
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('html', data)


class TestUrlViewTests(TestCase):
    """Test URL testing endpoint."""

    def test_get_request_rejected(self):
        """GET requests should be rejected."""
        response = self.client.get('/test-url/')
        data = response.json()
        self.assertFalse(data['success'])

    def test_empty_url(self):
        """Empty URL should return error."""
        response = self.client.post(
            '/test-url/',
            data=json.dumps({'url': ''}),
            content_type='application/json'
        )
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('URL is required', data['error'])

    def test_unknown_source_url(self):
        """URL from unknown source should return error."""
        response = self.client.post(
            '/test-url/',
            data=json.dumps({'url': 'https://unknownnews.com/article'}),
            content_type='application/json'
        )
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('No source found', data['error'])


# =============================================================================
# MODEL TESTS
# =============================================================================

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

    def test_article_str(self):
        """String representation should be the title."""
        article = Article.objects.create(
            title="Test Title",
            pub_date=timezone.now(),
            url="https://example.com/article"
        )
        self.assertEqual(str(article), "Test Title")

    def test_article_ordering(self):
        """Articles should be ordered by created_at descending."""
        from datetime import timedelta

        now = timezone.now()
        older = Article.objects.create(
            title="Older",
            pub_date=now,
            url="https://example.com/1",
            created_at=now - timedelta(hours=1)
        )
        newer = Article.objects.create(
            title="Newer",
            pub_date=now,
            url="https://example.com/2",
            created_at=now
        )

        articles = list(Article.objects.all())
        self.assertEqual(articles[0], newer)
        self.assertEqual(articles[1], older)

    def test_optional_fields_nullable(self):
        """Optional fields should accept null values."""
        article = Article.objects.create(
            title="Minimal Article",
            pub_date=timezone.now(),
            url="https://example.com/article",
            content=None,
            summary=None,
            ai_title=None,
            image_url=None
        )
        self.assertIsNone(article.content)
        self.assertIsNone(article.summary)

    def test_topics_default(self):
        """Topics should default to empty list."""
        article = Article.objects.create(
            title="No Topics",
            pub_date=timezone.now(),
            url="https://example.com/article"
        )
        self.assertEqual(article.topics, [])

    def test_topics_json_field(self):
        """Topics should store JSON list."""
        article = Article.objects.create(
            title="With Topics",
            pub_date=timezone.now(),
            url="https://example.com/article",
            topics=['Politics', 'Technology', 'Climate']
        )
        self.assertEqual(len(article.topics), 3)
        self.assertIn('Politics', article.topics)

    def test_source_default(self):
        """Source should default to 'apnews'."""
        article = Article.objects.create(
            title="Default Source",
            pub_date=timezone.now(),
            url="https://example.com/article"
        )
        self.assertEqual(article.source, 'apnews')


# =============================================================================
# FETCH ARTICLE PIPELINE TESTS
# =============================================================================

class FetchArticlePipelineTests(TestCase):
    """Test the article fetching pipeline."""

    @patch('chomp.views.get_source')
    def test_skips_seen_urls(self, mock_get_source):
        """Should skip URLs that are in the seen list."""
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
        """Should return article with generated summary."""
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

    @patch('chomp.views.get_source')
    def test_handles_failed_extraction(self, mock_get_source):
        """Should continue to next article on extraction failure."""
        mock_source = MagicMock()
        mock_source.search.return_value = ['https://example.com/bad', 'https://example.com/good']
        mock_source.fetch.return_value = '<html></html>'
        mock_source.extract.side_effect = [
            {'title': None, 'url': None},  # First article fails
            {'title': 'Good Article', 'url': 'https://example.com/good', 'content': 'Content'}
        ]
        mock_get_source.return_value = mock_source

        with patch('chomp.views.generate_summary', return_value=None):
            result = fetch_article_from_sources(['testsource'], [])

        self.assertIsNotNone(result)
        self.assertEqual(result.title, 'Good Article')

    @patch('chomp.views.get_source')
    def test_returns_none_when_no_articles(self, mock_get_source):
        """Should return None when no sources have articles."""
        mock_source = MagicMock()
        mock_source.search.return_value = []
        mock_get_source.return_value = mock_source

        result = fetch_article_from_sources(['testsource'], [])

        self.assertIsNone(result)
