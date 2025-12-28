"""
Comprehensive test suite for the chomp app.

Tests cover:
- URL normalization for deduplication
- Session-based URL tracking
- LLM integration (mocked)
- News source detection and extraction
- Geolocation
- Django views
- Article model
- Full fetch pipeline
- Edge cases and error handling
"""
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from unittest.mock import patch, MagicMock
from datetime import timedelta
import json

from .models import Article
from .views import normalize_url, get_seen_urls, mark_url_seen, fetch_article_from_sources
from .sources import (
    get_source, get_source_for_url, find_nearest_source,
    get_local_sources_with_locations, NEWS_SOURCES
)
from .utils import generate_summary, extract_topics_with_llm


# =============================================================================
# URL NORMALIZATION TESTS
# =============================================================================

class NormalizeUrlTests(TestCase):
    """Test URL normalization for duplicate detection."""

    def test_combined_fragment_and_encoding(self):
        """Both fragment and percent-encoding should be handled."""
        url = "https://example.com/article%2F123#section"
        expected = "https://example.com/article/123"
        self.assertEqual(normalize_url(url), expected)

    def test_url_with_just_fragment(self):
        """URL with fragment should have fragment stripped."""
        url = "https://example.com/article/123#comments-section"
        expected = "https://example.com/article/123"
        self.assertEqual(normalize_url(url), expected)

    def test_url_with_just_encoding(self):
        """URL with percent-encoding should be decoded."""
        url = "https://example.com/article%2F123"
        expected = "https://example.com/article/123"
        self.assertEqual(normalize_url(url), expected)

    def test_url_with_query_params(self):
        """URL with query parameters should be preserved."""
        url = "https://example.com/article/123?page=2&sort= newest"
        expected = "https://example.com/article/123?page=2&sort= newest"
        self.assertEqual(normalize_url(url), expected)

    def test_url_with_mixed_query_and_fragment(self):
        """URL with both query and fragment should handle both."""
        url = "https://example.com/article/123?ref=share#section"
        expected = "https://example.com/article/123?ref=share"
        self.assertEqual(normalize_url(url), expected)

    def test_url_with_unicode_characters(self):
        """URL with unicode characters should be handled gracefully."""
        url = "https://example.com/article/caf%C3%A9-news"
        expected = "https://example.com/article/caf\u00e9-news"
        self.assertEqual(normalize_url(url), expected)

    def test_url_with_double_encoding(self):
        """URL with double-encoded characters should be decoded."""
        url = "https://example.com/article/%252Fpath"
        expected = "https://example.com/article/%2Fpath"
        self.assertEqual(normalize_url(url), expected)

    def test_plain_url_unchanged(self):
        """Plain URL without fragment or encoding should remain unchanged."""
        url = "https://example.com/article/123"
        self.assertEqual(normalize_url(url), url)


# =============================================================================
# SESSION URL TRACKING TESTS
# =============================================================================

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

    def test_add_first_url_to_empty_session(self):
        """Should add first URL to empty session."""
        request = MagicMock()
        request.session = {'seen_urls': {}}

        mark_url_seen(request, 'https://example.com/article', 'world')

        self.assertEqual(len(request.session['seen_urls']['world']), 1)
        self.assertIn('https://example.com/article', request.session['seen_urls']['world'])

    def test_prevent_duplicate_urls(self):
        """Should not add duplicate URL to same category."""
        request = MagicMock()
        request.session = {'seen_urls': {'world': ['https://example.com/article']}}

        mark_url_seen(request, 'https://example.com/article', 'world')

        self.assertEqual(len(request.session['seen_urls']['world']), 1)

    def test_separate_tracking_per_category(self):
        """Should track URLs separately for different categories."""
        request = MagicMock()
        request.session = {'seen_urls': {'world': [], 'color': []}}

        mark_url_seen(request, 'https://example.com/world-article', 'world')
        mark_url_seen(request, 'https://example.com/color-article', 'color')

        self.assertEqual(len(request.session['seen_urls']['world']), 1)
        self.assertEqual(len(request.session['seen_urls']['color']), 1)
        self.assertIn('https://example.com/world-article', request.session['seen_urls']['world'])
        self.assertNotIn('https://example.com/world-article', request.session['seen_urls']['color'])

    def test_handle_nonexistent_category(self):
        """Should handle non-existent category gracefully."""
        request = MagicMock()
        request.session = {'seen_urls': {}}

        mark_url_seen(request, 'https://example.com/article', 'newcategory')

        self.assertEqual(len(request.session['seen_urls']['newcategory']), 1)

    def test_get_seen_urls_empty_category(self):
        """Should return empty list for non-existent category."""
        request = MagicMock()
        request.session = {'seen_urls': {}}

        result = get_seen_urls(request, 'world')

        self.assertEqual(result, [])

    def test_get_seen_urls_existing_category(self):
        """Should return list for existing category."""
        request = MagicMock()
        request.session = {'seen_urls': {'world': ['https://example.com/1', 'https://example.com/2']}}

        result = get_seen_urls(request, 'world')

        self.assertEqual(len(result), 2)

    def test_mark_url_seen_with_none_url(self):
        """Should handle None URL gracefully."""
        request = MagicMock()
        request.session = {'seen_urls': {'world': []}}

        mark_url_seen(request, None, 'world')

        # Should not raise and should not add anything
        self.assertEqual(len(request.session['seen_urls']['world']), 0)


# =============================================================================
# SOURCE FACTORY TESTS
# =============================================================================

class SourceFactoryTests(TestCase):
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

    def test_get_invalid_source(self):
        """Should return None for invalid source name."""
        source = get_source('nonexistent')
        self.assertIsNone(source)

    def test_list_all_available_sources(self):
        """Should list all available sources in registry."""
        self.assertEqual(len(NEWS_SOURCES), 14)
        self.assertIn('apnews', NEWS_SOURCES)
        self.assertIn('bbc', NEWS_SOURCES)
        self.assertIn('reuters', NEWS_SOURCES)
        self.assertIn('austinchronicle', NEWS_SOURCES)
        self.assertIn('gothamist', NEWS_SOURCES)

    def test_get_local_sources_with_locations(self):
        """Should return local sources with location data."""
        sources = get_local_sources_with_locations()
        self.assertIsInstance(sources, list)
        self.assertGreater(len(sources), 0)

        # Check structure of returned sources
        for source in sources:
            self.assertIn('source_key', source)
            self.assertIn('name', source)
            self.assertIn('latitude', source)
            self.assertIn('longitude', source)
            self.assertIn('city', source)

    def test_domain_detection_all_sources(self):
        """Should detect correct source for all domain mappings."""
        test_cases = [
            ('https://bbc.com/news/123', 'bbc'),
            ('https://www.bbc.co.uk/news', 'bbc'),
            ('https://reuters.com/article/123', 'reuters'),
            ('https://www.reuters.com/article/123', 'reuters'),
            ('https://austinchronicle.com/article/123', 'austinchronicle'),
            ('https://doorcountypulse.com/article/123', 'doorcountypulse'),
            ('https://urbanmilwaukee.com/article/123', 'urbanmilwaukee'),
            ('https://stlmag.com/article/123', 'stlmag'),
            ('https://blockclubchicago.org/article/123', 'blockclubchicago'),
            ('https://gothamist.com/article/123', 'gothamist'),
            ('https://303magazine.com/article/123', '303magazine'),
            ('https://iexaminer.org/article/123', 'iexaminer'),
            ('https://thegambit.com/article/123', 'gambit'),
            ('https://slugmag.com/article/123', 'slugmag'),
            ('https://folioweekly.com/article/123', 'folioweekly'),
        ]

        for url, expected_key in test_cases:
            with self.subTest(url=url):
                source = get_source_for_url(url)
                self.assertIsNotNone(source, f"Source not found for {url}")
                self.assertEqual(source.source_key, expected_key)

    def test_domain_detection_unknown_domain(self):
        """Should return None for unknown domain."""
        source = get_source_for_url("https://unknownsite.com/article/123")
        self.assertIsNone(source)


# =============================================================================
# SOURCE EXTRACTION TESTS
# =============================================================================

class APNewsExtractionTests(TestCase):
    """Test article extraction from HTML."""

    def setUp(self):
        self.source = get_source('apnews')

    @patch('chomp.utils.extract_topics_with_llm', return_value=['Politics', 'World'])
    def test_extract_basic_article(self, mock_topics):
        """Should extract article data from AP News HTML."""
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

        result = self.source.extract(html)

        self.assertEqual(result['title'], 'Test Article Title')
        self.assertEqual(result['url'], 'https://apnews.com/article/test-123')
        self.assertIn('article content', result['content'])
        self.assertEqual(result['image_url'], 'https://example.com/image.jpg')

    @patch('chomp.utils.extract_topics_with_llm', return_value=[])
    def test_extract_missing_title(self, mock_topics):
        """Should return None for missing title."""
        html = '''
        <html>
        <head>
            <meta property="og:url" content="https://apnews.com/article/test-123">
        </head>
        <body>
            <div class="RichTextStoryBody RichTextBody">Content here</div>
        </body>
        </html>
        '''

        result = self.source.extract(html)

        self.assertIsNone(result['title'])

    @patch('chomp.utils.extract_topics_with_llm', return_value=[])
    def test_extract_missing_content(self, mock_topics):
        """Should return None for missing content."""
        html = '''
        <html>
        <head>
            <meta property="og:title" content="Test Title">
            <meta property="og:url" content="https://apnews.com/article/test-123">
        </head>
        <body>
        </body>
        </html>
        '''

        result = self.source.extract(html)

        self.assertEqual(result['title'], 'Test Title')
        self.assertIsNone(result['content'])

    @patch('chomp.utils.extract_topics_with_llm', return_value=['Tech'])
    def test_extract_video_poster_image(self, mock_topics):
        """Should extract video poster as image URL."""
        html = '''
        <html>
        <head>
            <meta property="og:title" content="Test Article">
            <meta property="og:url" content="https://apnews.com/article/test">
        </head>
        <body>
            <div class="Page-content">
                <bsp-jw-player poster="https://example.com/video-thumb.jpg"></bsp-jw-player>
            </div>
            <div class="RichTextStoryBody RichTextBody">Content</div>
        </body>
        </html>
        '''

        result = self.source.extract(html)

        self.assertEqual(result['image_url'], 'https://example.com/video-thumb.jpg')

    @patch('chomp.utils.extract_topics_with_llm', return_value=[])
    def test_extract_lazy_load_image(self, mock_topics):
        """Should extract lazy-loaded image URL."""
        html = '''
        <html>
        <head>
            <meta property="og:title" content="Test Article">
            <meta property="og:url" content="https://apnews.com/article/test">
        </head>
        <body>
            <div class="Page-content">
                <picture>
                    <img class="Image" data-flickity-lazyload="https://example.com/lazy.jpg">
                </picture>
            </div>
            <div class="RichTextStoryBody RichTextBody">Content</div>
        </body>
        </html>
        '''

        result = self.source.extract(html)

        self.assertEqual(result['image_url'], 'https://example.com/lazy.jpg')

    @patch('chomp.utils.extract_topics_with_llm', return_value=[])
    def test_extract_pub_date_parsing(self, mock_topics):
        """Should parse publication date correctly."""
        html = '''
        <html>
        <head>
            <meta property="og:title" content="Test Article">
            <meta property="og:url" content="https://apnews.com/article/test">
            <meta property="article:published_time" content="2024-06-15T14:30:00Z">
        </head>
        <body>
            <div class="RichTextStoryBody RichTextBody">Content</div>
        </body>
        </html>
        '''

        result = self.source.extract(html)

        self.assertIsNotNone(result['pub_date'])
        self.assertEqual(result['pub_date'].year, 2024)
        self.assertEqual(result['pub_date'].month, 6)
        self.assertEqual(result['pub_date'].day, 15)

    @patch('chomp.utils.extract_topics_with_llm', return_value=[])
    def test_extract_empty_html(self, mock_topics):
        """Should handle empty HTML gracefully."""
        html = '<html><body></body></html>'

        result = self.source.extract(html)

        self.assertIsNotNone(result)
        self.assertIn('title', result)
        self.assertIn('url', result)


# =============================================================================
# GEOLOCATION TESTS
# =============================================================================

class GeolocationTests(TestCase):
    """Test geolocation and nearest source finding."""

    def test_find_nearest_source_austin(self):
        """Should find Austin Chronicle as nearest for Austin coordinates."""
        result = find_nearest_source(30.2672, -97.7431)
        self.assertIsNotNone(result)
        self.assertEqual(result['source_key'], 'austinchronicle')
        self.assertIn('distance_km', result)

    def test_find_nearest_source_chicago(self):
        """Should find Block Club Chicago as nearest for Chicago coordinates."""
        result = find_nearest_source(41.8781, -87.6298)
        self.assertIsNotNone(result)
        self.assertIn(result['source_key'], ['blockclubchicago', 'gothamist', 'stlmag'])

    def test_find_nearest_source_distance_calculation(self):
        """Should return valid distance in km."""
        # Use coordinates slightly offset from Austin to ensure non-zero distance
        result = find_nearest_source(30.2682, -97.7431)
        self.assertIsInstance(result['distance_km'], float)
        self.assertGreater(result['distance_km'], 0)
        self.assertLess(result['distance_km'], 10000)  # Should be less than Earth's diameter

    def test_find_nearest_source_returns_none_with_no_sources(self):
        """Should return None when no local sources available."""
        # This tests the edge case by mocking get_local_sources_with_locations
        with patch('chomp.sources.get_local_sources_with_locations', return_value=[]):
            result = find_nearest_source(0, 0)
            self.assertIsNone(result)


# =============================================================================
# VIEW TESTS
# =============================================================================

class ViewTests(TestCase):
    """Test Django view endpoints."""

    def setUp(self):
        self.client = Client()

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

    def test_refresh_get_method_returns_405(self):
        """Refresh endpoint should return 405 for GET requests."""
        response = self.client.get('/refresh/world/')
        self.assertEqual(response.status_code, 405)

    def test_refresh_invalid_category_returns_error(self):
        """Refresh endpoint should return error for invalid category."""
        response = self.client.post('/refresh/invalid/')
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    def test_nearest_source_get_method_returns_405(self):
        """Nearest source endpoint should return 405 for GET requests."""
        response = self.client.get('/nearest-source/')
        self.assertEqual(response.status_code, 405)

    def test_nearest_source_invalid_location_data(self):
        """Nearest source should return error for invalid location."""
        response = self.client.post(
            '/nearest-source/',
            data=json.dumps({'invalid': 'data'}),
            content_type='application/json'
        )
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    def test_nearest_source_missing_coordinates(self):
        """Nearest source should return error for missing coordinates."""
        response = self.client.post(
            '/nearest-source/',
            data=json.dumps({}),
            content_type='application/json'
        )
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    def test_fetch_from_source_get_method_returns_405(self):
        """Fetch from source endpoint should return 405 for GET requests."""
        response = self.client.get('/fetch-local/apnews/')
        self.assertEqual(response.status_code, 405)

    def test_fetch_from_invalid_source(self):
        """Should return error for invalid source name."""
        response = self.client.post('/fetch-local/nonexistent/')
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    def test_test_url_get_method_returns_405(self):
        """Test URL endpoint should return 405 for GET requests."""
        response = self.client.get('/test-url/')
        self.assertEqual(response.status_code, 405)

    def test_test_url_missing_url(self):
        """Test URL endpoint should return error for missing URL."""
        response = self.client.post(
            '/test-url/',
            data=json.dumps({}),
            content_type='application/json'
        )
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    def test_test_url_empty_url(self):
        """Test URL endpoint should return error for empty URL."""
        response = self.client.post(
            '/test-url/',
            data=json.dumps({'url': '   '}),
            content_type='application/json'
        )
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    @override_settings(SKIP_CRAWL=True)
    def test_refresh_skips_crawl_when_setting_enabled(self):
        """Refresh should use mock data when SKIP_CRAWL is True."""
        response = self.client.post('/refresh/world/')
        data = response.json()
        self.assertTrue(data['success'])


# =============================================================================
# ARTICLE MODEL TESTS
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
        self.assertEqual(str(article), "Test Article")

    def test_create_article_with_all_fields(self):
        """Should create article with all optional fields."""
        article = Article.objects.create(
            title="Full Article",
            pub_date=timezone.now(),
            url="https://example.com/article",
            content="Article content here",
            summary="AI generated summary",
            ai_title="AI Title",
            image_url="https://example.com/image.jpg",
            source="apnews",
            topics=["Politics", "World"]
        )
        self.assertEqual(article.title, "Full Article")
        self.assertEqual(article.content, "Article content here")
        self.assertEqual(article.summary, "AI generated summary")
        self.assertEqual(article.ai_title, "AI Title")
        self.assertEqual(article.image_url, "https://example.com/image.jpg")
        self.assertEqual(article.source, "apnews")
        self.assertEqual(article.topics, ["Politics", "World"])

    def test_topics_json_field(self):
        """Should store topics as JSON list."""
        article = Article.objects.create(
            title="JSON Topics Test",
            pub_date=timezone.now(),
            url="https://example.com/article",
            topics=["Tech", "Science", "Innovation"]
        )
        # Refresh from database
        article.refresh_from_db()
        self.assertEqual(article.topics, ["Tech", "Science", "Innovation"])

    def test_topics_empty_by_default(self):
        """Topics should be empty list by default."""
        article = Article.objects.create(
            title="Default Topics Test",
            pub_date=timezone.now(),
            url="https://example.com/article"
        )
        self.assertEqual(article.topics, [])

    def test_default_ordering(self):
        """Articles should be ordered by -created_at by default."""
        now = timezone.now()
        article1 = Article.objects.create(
            title="Article 1",
            pub_date=now,
            url="https://example.com/1",
            created_at=now - timedelta(seconds=1)
        )
        article2 = Article.objects.create(
            title="Article 2",
            pub_date=now,
            url="https://example.com/2",
            created_at=now
        )

        articles = list(Article.objects.all())
        self.assertEqual(articles[0], article2)  # Most recent first
        self.assertEqual(articles[1], article1)


# =============================================================================
# LLM SUMMARY TESTS
# =============================================================================

class GenerateSummaryTests(TestCase):
    """Test LLM summary generation with mocked OpenAI API."""

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_successful_summary_generation(self, mock_openai):
        """Should parse LLM response correctly."""
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
        mock_client = MagicMock()
        mock_client.responses.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        result = generate_summary("Article content")
        self.assertIsNone(result)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_handles_empty_response(self, mock_openai):
        """Should handle empty LLM response."""
        mock_response = MagicMock()
        mock_response.output_text = ""

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        result = generate_summary("Article content")
        self.assertIsNotNone(result)
        self.assertIsNone(result['ai_title'])
        self.assertEqual(result['summary'], "")

    def test_generate_summary_no_content(self):
        """Should return None for empty content."""
        result = generate_summary("")
        self.assertIsNone(result)

        result = generate_summary(None)
        self.assertIsNone(result)

    def test_generate_summary_no_api_key(self):
        """Should return None when API key is not set."""
        # Temporarily remove API key
        import os
        original_key = os.environ.pop('OPENAI_API_KEY', None)
        try:
            result = generate_summary("Article content")
            self.assertIsNone(result)
        finally:
            if original_key:
                os.environ['OPENAI_API_KEY'] = original_key


# =============================================================================
# LLM TOPIC EXTRACTION TESTS
# =============================================================================

class ExtractTopicsTests(TestCase):
    """Test LLM topic extraction with mocked OpenAI API."""

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_successful_topic_extraction(self, mock_openai):
        """Should extract topics from article content."""
        mock_response = MagicMock()
        mock_response.output_text = """Politics
Technology
Economy"""

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        result = extract_topics_with_llm("Article about politics and technology...")

        self.assertEqual(len(result), 3)
        self.assertIn('Politics', result)
        self.assertIn('Technology', result)
        self.assertIn('Economy', result)

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_handles_api_error(self, mock_openai):
        """Should return empty list on API error."""
        mock_client = MagicMock()
        mock_client.responses.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        result = extract_topics_with_llm("Article content")
        self.assertEqual(result, [])

    def test_extract_topics_no_content(self):
        """Should return empty list for empty content."""
        result = extract_topics_with_llm("")
        self.assertEqual(result, [])

        result = extract_topics_with_llm(None)
        self.assertEqual(result, [])

    def test_extract_topics_no_api_key(self):
        """Should return empty list when API key is not set."""
        import os
        original_key = os.environ.pop('OPENAI_API_KEY', None)
        try:
            result = extract_topics_with_llm("Article content")
            self.assertEqual(result, [])
        finally:
            if original_key:
                os.environ['OPENAI_API_KEY'] = original_key

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'})
    @patch('chomp.utils.OpenAI')
    def test_handles_malformed_topic_response(self, mock_openai):
        """Should handle malformed topic response gracefully."""
        mock_response = MagicMock()
        mock_response.output_text = "   "  # Just whitespace

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        result = extract_topics_with_llm("Article content")
        self.assertEqual(result, [])


# =============================================================================
# FETCH PIPELINE TESTS
# =============================================================================

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

    @patch('chomp.views.get_source')
    def test_returns_none_when_all_sources_empty(self, mock_get_source):
        """Should return None when all sources return empty."""
        mock_source = MagicMock()
        mock_source.search.return_value = []
        mock_get_source.return_value = mock_source

        result = fetch_article_from_sources(['testsource'], [])

        self.assertIsNone(result)

    @patch('chomp.views.get_source')
    def test_skips_invalid_source(self, mock_get_source):
        """Should skip sources that return None."""
        mock_get_source.side_effect = [None, None]

        result = fetch_article_from_sources(['invalid1', 'invalid2'], [])

        self.assertIsNone(result)

    @patch('chomp.views.get_source')
    @patch('chomp.views.generate_summary')
    def test_skips_seen_after_normalization(self, mock_summary, mock_get_source):
        """Should skip URLs that match after normalization."""
        mock_source = MagicMock()
        mock_source.search.return_value = ['https://example.com/article%2F123']
        mock_source.fetch.return_value = '<html></html>'
        mock_source.extract.return_value = {
            'title': 'Test Article',
            'url': 'https://example.com/article%2F123',
            'content': 'Article content',
            'pub_date': None,
            'image_url': None,
            'topics': []
        }
        mock_get_source.return_value = mock_source

        # Seen URL without encoding
        seen_urls = ['https://example.com/article/123']
        result = fetch_article_from_sources(['testsource'], seen_urls)

        self.assertIsNone(result)
        mock_source.fetch.assert_not_called()

    @patch('chomp.views.get_source')
    @patch('chomp.views.generate_summary')
    def test_continues_to_next_on_extract_failure(self, mock_summary, mock_get_source):
        """Should continue to next URL when extraction fails."""
        mock_source = MagicMock()
        mock_source.search.return_value = ['https://example.com/first', 'https://example.com/second']
        mock_source.fetch.return_value = '<html></html>'
        mock_source.extract.side_effect = [
            {'title': None, 'url': 'https://example.com/first'},  # Fails
            {'title': 'Second Article', 'url': 'https://example.com/second', 'content': 'Content'}
        ]
        mock_get_source.return_value = mock_source

        mock_summary.return_value = {'ai_title': 'Title', 'summary': 'Summary'}

        result = fetch_article_from_sources(['testsource'], [])

        self.assertIsNotNone(result)
        self.assertEqual(result.title, 'Second Article')

    @patch('chomp.views.get_source')
    @patch('chomp.views.generate_summary')
    def test_graceful_degradation_on_summary_failure(self, mock_summary, mock_get_source):
        """Should return article even if summary generation fails."""
        mock_source = MagicMock()
        mock_source.search.return_value = ['https://example.com/article']
        mock_source.fetch.return_value = '<html></html>'
        mock_source.extract.return_value = {
            'title': 'Test Article',
            'url': 'https://example.com/article',
            'content': 'Article content',
            'pub_date': None,
            'image_url': None,
            'topics': []
        }
        mock_get_source.return_value = mock_source

        mock_summary.return_value = None  # Summary fails

        result = fetch_article_from_sources(['testsource'], [])

        self.assertIsNotNone(result)
        self.assertEqual(result.title, 'Test Article')
        self.assertEqual(result.summary, '')  # Empty summary
        self.assertEqual(result.ai_title, '')  # Empty ai_title


# =============================================================================
# SOURCE SEARCH TESTS
# =============================================================================

class SourceSearchTests(TestCase):
    """Test source search functionality."""

    @patch('chomp.sources.apnews.requests')
    def test_apnews_search_returns_article_urls(self, mock_requests):
        """AP News search should return list of article URLs."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <body>
            <div class="PagePromo-title">
                <a class="Link" href="/article/test-123">Test Article</a>
            </div>
            <div class="PagePromo-title">
                <a class="Link" href="/article/test-456">Another Article</a>
            </div>
        </body>
        </html>
        '''
        mock_requests.get.return_value = mock_response

        source = get_source('apnews')
        result = source.search()

        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertTrue(all('/article/' in url for url in result))

    @patch('chomp.sources.apnews.requests')
    def test_apnews_search_skips_non_articles(self, mock_requests):
        """AP News search should skip video/gallery URLs."""
        mock_response = MagicMock()
        mock_response.text = '''
        <html>
        <body>
            <div class="PagePromo-title">
                <a class="Link" href="/video/123">Video Page</a>
            </div>
            <div class="PagePromo-title">
                <a class="Link" href="/gallery/456">Gallery Page</a>
            </div>
            <div class="PagePromo-title">
                <a class="Link" href="/article/789">Article</a>
            </div>
        </body>
        </html>
        '''
        mock_requests.get.return_value = mock_response

        source = get_source('apnews')
        result = source.search()

        self.assertEqual(len(result), 1)
        self.assertIn('/article/789', result[0])

    @patch('chomp.sources.apnews.requests')
    def test_apnews_search_handles_empty_page(self, mock_requests):
        """AP News search should return empty list when no articles found."""
        mock_response = MagicMock()
        mock_response.text = '<html><body></body></html>'
        mock_requests.get.return_value = mock_response

        source = get_source('apnews')
        result = source.search()

        self.assertEqual(result, [])

    @patch('chomp.sources.apnews.requests.get')
    def test_apnews_search_handles_http_error(self, mock_get):
        """AP News search should return empty list on HTTP error."""
        import requests
        mock_get.side_effect = requests.RequestException("Connection Error")

        source = get_source('apnews')
        result = source.search()

        self.assertEqual(result, [])


# =============================================================================
# SOURCE FETCH TESTS
# =============================================================================

class SourceFetchTests(TestCase):
    """Test source fetch functionality."""

    @patch('requests.get')
    def test_fetch_returns_html_content(self, mock_get):
        """Should return HTML content from URL."""
        mock_response = MagicMock()
        mock_response.text = '<html><body>Test content</body></html>'
        mock_get.return_value = mock_response

        source = get_source('apnews')
        result = source.fetch('https://apnews.com/article/test')

        self.assertEqual(result, '<html><body>Test content</body></html>')
        mock_get.assert_called_once_with('https://apnews.com/article/test')

    @patch('requests.get')
    def test_fetch_handles_http_error(self, mock_get):
        """Should raise exception on HTTP error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response

        source = get_source('apnews')

        with self.assertRaises(Exception):
            source.fetch('https://apnews.com/article/notfound')
