import os
import urllib.parse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from django.utils import timezone
from openai import OpenAI


def get_first_search_result_url(query):
    """
    Search AP News and get the URL of the first article result.
    Skips non-article pages (videos, galleries, etc.)

    Args:
        query: Search query string

    Returns:
        str: URL of the first article result, or None if not found
    """
    # Build search URL
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://apnews.com/search?q={encoded_query}&s=3"

    print(f"Searching: {search_url}")

    # Fetch search results page
    response = requests.get(search_url)
    response.raise_for_status()

    # Parse search results
    soup = BeautifulSoup(response.text, 'html.parser')

    # Find all results with PagePromo-title
    promo_titles = soup.find_all('div', class_='PagePromo-title')
    if not promo_titles:
        print("No search results found")
        return None

    # Loop through results to find first valid article URL
    for promo_title in promo_titles:
        link_element = promo_title.find('a', class_='Link')
        if not link_element:
            continue

        article_url = link_element.get('href')
        if not article_url:
            continue

        # Handle relative URLs
        if not article_url.startswith('http'):
            article_url = f"https://apnews.com{article_url}"

        # Check if it's an article URL (not video, gallery, etc.)
        if '/article/' in article_url:
            print(f"Found article URL: {article_url}")
            return article_url
        else:
            print(f"Skipping non-article URL: {article_url}")

    print("No article URLs found in search results")
    return None


def extract_apnews_content(html_string):
    """
    Extract AP News article data from HTML string.

    Args:
        html_string: HTML content as string

    Returns:
        dict: Dictionary containing title, url, pub_date, and content
    """
    soup = BeautifulSoup(html_string, 'html.parser')

    # Extract meta tags
    title_tag = soup.find('meta', property='og:title')
    url_tag = soup.find('meta', property='og:url')
    pub_date_tag = soup.find('meta', property='article:published_time')

    # Extract content div
    content_div = soup.find('div', class_='RichTextStoryBody RichTextBody')

    # Parse publication date
    pub_date = None
    if pub_date_tag:
        pub_date_str = pub_date_tag.get('content')
        if pub_date_str:
            try:
                # Parse ISO format datetime
                pub_date = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                # Convert to Django timezone-aware datetime
                if timezone.is_naive(pub_date):
                    pub_date = timezone.make_aware(pub_date)
            except (ValueError, AttributeError):
                pub_date = timezone.now()

    # Build result dictionary
    result = {
        'title': title_tag.get('content') if title_tag else None,
        'url': url_tag.get('content') if url_tag else None,
        'pub_date': pub_date,
        'content': content_div.get_text(strip=True) if content_div else None
    }

    return result


def generate_summary(content):
    """
    Generate a summary and three-word title for article content using OpenAI.

    Args:
        content: Article content text

    Returns:
        dict: {'ai_title': str, 'summary': str} or None if generation fails
    """
    if not content:
        print("No content provided for summary generation")
        return None

    try:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("ERROR: OPENAI_API_KEY environment variable not set")
            return None

        print(f"Generating summary for content ({len(content)} chars)...")
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are a news summarizer.
Condense articles into exactly 3 lines.
Use specific objects and details from the article.
Favor imagery and paint a picture. Always be objective.
Also provide a three word title.
Ignore ads and unrelated info.

Output format:
TITLE: <three word title>
<summary line 1>
<summary line 2>
<summary line 3>"""
                },
                {
                    "role": "user",
                    "content": f"Summarize this article:\n\n{content[:4000]}"
                }
            ],
            temperature=0.7,
            max_tokens=250
        )

        result = response.choices[0].message.content.strip()
        print(f"Successfully generated: {result[:100]}...")

        # Parse the result
        lines = result.split('\n')
        ai_title = None
        summary_lines = []

        for line in lines:
            line = line.strip()
            if line.startswith('TITLE:'):
                ai_title = line.replace('TITLE:', '').strip()
            elif line and not line.startswith('TITLE:'):
                summary_lines.append(line)

        summary = '\n'.join(summary_lines)

        return {
            'ai_title': ai_title,
            'summary': summary
        }

    except Exception as e:
        print(f"Failed to generate summary: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


def search_and_extract_article(query):
    """
    Search AP News for a query and extract the first result's article data.

    Args:
        query: Search query string

    Returns:
        dict: Extracted article data or None if search/extraction fails
    """
    # Get first search result URL
    article_url = get_first_search_result_url(query)

    if not article_url:
        return None

    # Fetch article page
    response = requests.get(article_url)
    response.raise_for_status()

    # Extract content
    extracted_data = extract_apnews_content(response.text)

    # Generate summary and title if content exists
    if extracted_data and extracted_data.get('content'):
        ai_data = generate_summary(extracted_data['content'])
        if ai_data:
            extracted_data['summary'] = ai_data.get('summary')
            extracted_data['ai_title'] = ai_data.get('ai_title')

    return extracted_data
