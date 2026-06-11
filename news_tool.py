import httpx
import os
from datetime import date

NEWSAPI_KEY = os.getenv("NEWS_API_KEY")

CATEGORY_MAP = {
    "karnataka": {"q": "Karnataka", "language": "en"},
    "india": {"q": "India", "language": "en"},
    "sports": {"q": "cricket OR IPL OR sports India", "language": "en"},
    "technology": {"q": "technology India", "language": "en"},
    "general": {"q": "India", "language": "en"},
}


async def fetch_headlines(category: str = "general", count: int = 5) -> str:
    """
    Fetch top headlines and return as a plain-text list.
    The LLM will receive this and summarize in Kannada.
    """
    params = CATEGORY_MAP.get(category.lower(), CATEGORY_MAP["general"])

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": params["q"],
                "language": params["language"],
                "sortBy": "publishedAt",
                "pageSize": count,
                "apiKey": NEWSAPI_KEY,
            },
        )
        r.raise_for_status()
        data = r.json()

    articles = data.get("articles", [])
    if not articles:
        return "No news found for this category today."

    lines = []
    for i, a in enumerate(articles[:count], 1):
        title = a.get("title", "").split(" - ")[0].strip()
        source = a.get("source", {}).get("name", "")
        lines.append(f"{i}. {title} ({source})")

    today = date.today().strftime("%B %d, %Y")
    return f"Top {category} headlines for {today}:\n" + "\n".join(lines)


# Tool schema for Pipecat LLM tool calling
FETCH_NEWS_TOOL = {
    "type": "function",
    "function": {
        "name": "fetch_headlines",
        "description": (
            "Fetch today's top news headlines for a given category. "
            "Call this when the user asks for news, headlines, or 'what happened today'. "
            "Categories: karnataka, india, sports, technology, general."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["karnataka", "india", "sports", "technology", "general"],
                    "description": "News category based on what the user asked for.",
                }
            },
            "required": ["category"],
        },
    },
}
