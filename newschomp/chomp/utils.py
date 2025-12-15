import os
from openai import OpenAI


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

        response = client.responses.create(
            model="gpt-5.2",
            reasoning={"effort": "medium"},
            text={"verbosity": "low"},
            input=[
                {
                    "role": "system",
                    "content": """You are a news article condenser.
Summarize the article into 3 SHORT, concise lines.
Keep these lines as SMALL as you can while still portraying the news accurately.
Include details.
KEEP LINES TINY.
Express the main idea.
Cut filler. Be objective. Make it MINIMAL.
Finally, provide a unique, 4 word title.
Present the news as an original source. Do not reference 'the article' explicitly.

Output format:
TITLE: <4 word title>
<summary line 1>
<summary line 2>
<summary line 3>"""
                },
                {
                    "role": "user",
                    "content": f"Summarize this article:\n\n{llm_content}"
                }
            ]
        )

        result = response.output_text.strip()
        print(f"LLM raw response: '{result}'")

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
        list: List of topic strings (4-6 topics), or empty list if extraction fails
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

        response = client.responses.create(
            model="gpt-5.2",
            reasoning={"effort": "medium"},
            text={"verbosity": "low"},
            input=[
                {
                    "role": "system",
                    "content": """Extract 3 or 4 topic tags from news articles.
Tags should be reusable across articles: locations (Gaza, Chicago), figures (Trump, Musk), or general categories (Crime, Weather, Tech).
1 word each, maybe 2. One per line. No bullets."""
                },
                {
                    "role": "user",
                    "content": f"Extract topics from this article:\n\n{llm_content}"
                }
            ]
        )

        result = response.output_text.strip()
        print(f"LLM topic extraction result: {result}")

        # Parse topics from result (one per line)
        topics = [line.strip() for line in result.split('\n') if line.strip()]

        print(f"Extracted topics: {topics}")
        return topics

    except Exception as e:
        print(f"Failed to extract topics: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []

