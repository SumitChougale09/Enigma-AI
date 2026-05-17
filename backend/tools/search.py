"""
Tavily Web Search Tool
──────────────────────
Searches the web using Tavily API and returns structured results
including content snippets that can be used directly as LLM context.

Key insight: Tavily returns a `content` field per result (semantic snippet)
so we DON'T need to scrape pages ourselves for V1.
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


def search_web(query: str, max_results: int = 5, include_raw_content: bool = False) -> dict:
    """
    Search the web using Tavily API.
    
    Returns:
        dict with keys:
            - results: list of {title, url, content, score, raw_content?}
            - answer: Tavily's built-in AI answer (optional bonus context)
            - query: the original query
    """
    url = "https://api.tavily.com/search"

    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",  # Deep crawl — gets fresher, more current content
        "include_answer": True,       # Tavily's own AI summary as bonus signal
        "include_raw_content": include_raw_content,
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()

    data = response.json()

    # Structure the results cleanly
    results = []
    for r in data.get("results", []):
        result = {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),  # Semantic snippet — our main context
            "score": r.get("score", 0),
        }
        if include_raw_content and r.get("raw_content"):
            result["raw_content"] = r["raw_content"]
        results.append(result)

    return {
        "results": results,
        "answer": data.get("answer", ""),  # Tavily's own AI answer
        "query": query,
    }