import os
from openai import OpenAI
from .sources import get_source


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

        # Prepare content for LLM (truncate to 4000 chars)
        llm_content = content[:4000]

        print("=" * 80)
        print("ARTICLE CONTENT SENT TO LLM:")
        print("=" * 80)
        print(llm_content)
        print("=" * 80)

        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-5.1",
            messages=[
                {
                    "role": "system",
                    "content": """You are a news article condenser.
Summarize the articles into 3 lines.
Use specific details and facts from the article.
Be objective.
Also provide a unique, three-word title.
Present the news as an original source. Do not make explicit references to 'the article', for example.

Output format:
TITLE: <three word title>
<summary line 1>
<summary line 2>
<summary line 3>"""
                },
                {
                    "role": "user",
                    "content": f"Summarize this article:\n\n{llm_content}"
                }
            ],
            temperature=0.7,
            max_completion_tokens=250
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


def extract_topics_with_llm(content):
    """
    Extract topics/categories from article content using OpenAI.

    Args:
        content: Article content text or HTML

    Returns:
        list: List of topic strings (3-5 topics), or empty list if extraction fails
    """
    if not content:
        print("No content provided for topic extraction")
        return []

    try:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("ERROR: OPENAI_API_KEY environment variable not set")
            return []

        print(f"Extracting topics for content ({len(content)} chars)...")

        # Prepare content for LLM (truncate to 2000 chars - enough for topic detection)
        llm_content = content[:2000]

        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-5.1",
            messages=[
                {
                    "role": "system",
                    "content": """You are a news article topic classifier.
Analyze the article and identify 3-5 relevant topics.
Include both broad categories AND specific subjects mentioned in the article.
Examples:
- Broad: Politics, Technology, Climate
- Specific: Tesla, Ukraine War, Federal Reserve, Artificial Intelligence, COVID-19
Be specific and identify key people, places, organizations, or events when relevant.
Keep topics concise - 1-3 words per topic.
Return only the topics, one per line, no numbering or bullets."""
                },
                {
                    "role": "user",
                    "content": f"Extract topics from this article:\n\n{llm_content}"
                }
            ],
            temperature=0.3,
            max_completion_tokens=100
        )

        result = response.choices[0].message.content.strip()
        print(f"LLM topic extraction result: {result}")

        # Parse topics from result (one per line)
        topics = [line.strip() for line in result.split('\n') if line.strip()]

        # Limit to 5 topics maximum
        topics = topics[:5]

        print(f"Extracted topics: {topics}")
        return topics

    except Exception as e:
        print(f"Failed to extract topics: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []


def search_and_extract_article(query, source_name='apnews'):
    """
    Search a news source for a query and extract the first result's article data.

    Args:
        query: Search query string
        source_name: Name of the news source to use (default: 'apnews')

    Returns:
        dict: Extracted article data with 'source' key, or None if search/extraction fails
    """
    # Get the news source instance
    source = get_source(source_name)
    if not source:
        print(f"Unknown news source: {source_name}")
        return None

    # Use the source to search and extract
    extracted_data = source.search_and_extract(query)

    if not extracted_data:
        return None

    # Add source information to the data
    extracted_data['source'] = source.source_key

    # Generate summary and title if content exists
    if extracted_data.get('content'):
        ai_data = generate_summary(extracted_data['content'])
        if ai_data:
            extracted_data['summary'] = ai_data.get('summary')
            extracted_data['ai_title'] = ai_data.get('ai_title')

    return extracted_data
