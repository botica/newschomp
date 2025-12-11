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

        response = client.chat.completions.create(
            model="gpt-5.1",
            messages=[
                {
                    "role": "system",
                    "content": """You are a news article condenser.
Summarize the article into 3 concise lines.
Include specific details: people, places, things.  
Express the main idea of the article in those three lines.
Take the most interesting points made in the article and provide a comprehensive narrative for the reader. 
Cut filler. Be direct and objective.
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
            ],
            temperature=0.7,
            max_completion_tokens=250
        )

        result = response.choices[0].message.content.strip()
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

        response = client.chat.completions.create(
            model="gpt-5.1",
            messages=[
                {
                    "role": "system",
                    "content": """You are a news article topic tagger.
Extract 4-6 keyword tags that categorize this article for comparison with other articles.
Tags should be REUSABLE - the same tag should appear across many different articles on similar subjects.
Specific names are OK for: locations (Gaza, Chicago, Ukraine), major figures (Trump, Musk), organizations (NATO, FDA)
But categories should be general: Natural Disaster, Weather, Humanitarian Aid, Tech Industry, Climate, Crime
Bad tags: "Humanitarian crisis in Gaza", "Winter storm flooding" - these are too specific to reuse
Avoid subjective or interpretive tags like: Nostalgia, Controversy, Tragedy, Hope, Irony
Stick to factual, objective categories.
Think: what tags would someone use to filter or group news articles?
Keep tags to 1-2 words each.
Return only the tags, one per line, no numbering or bullets."""
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

        print(f"Extracted topics: {topics}")
        return topics

    except Exception as e:
        print(f"Failed to extract topics: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []

