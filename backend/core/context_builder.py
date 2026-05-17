"""
Context Builder
───────────────
Takes raw Tavily search results and builds a clean, numbered context block
that gets injected into the LLM prompt.

This is the CORE of "context engineering" — how you format and present
retrieved information to the LLM directly impacts answer quality.

Design decisions:
  - Number each source [1], [2], etc. so the LLM can cite them
  - Include title + URL + content snippet per source
  - Truncate content to avoid blowing the context window
  - Order by Tavily relevance score (already sorted by Tavily)
"""

MAX_CONTENT_LENGTH = 1500  # chars per source — prevents context window overflow


def build_context(search_results: dict) -> tuple[str, list[dict]]:
    """
    Build a numbered context block from Tavily search results.
    
    Args:
        search_results: dict from search_web() with 'results' and 'answer' keys
        
    Returns:
        tuple of:
            - context_text: formatted string ready for LLM prompt injection
            - sources: list of {index, title, url} for citation formatting
    """
    results = search_results.get("results", [])
    tavily_answer = search_results.get("answer", "")
    
    if not results:
        return "No search results found.", []
    
    context_parts = []
    sources = []
    
    # Add Tavily's AI answer as a bonus signal (if available)
    if tavily_answer:
        context_parts.append(
            f"[AI Search Summary]\n{tavily_answer}\n"
        )
    
    # Build numbered context from each source
    for i, result in enumerate(results, 1):
        title = result.get("title", "Unknown")
        url = result.get("url", "")
        content = result.get("content", "")
        
        # Truncate long content to stay within context limits
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "..."
        
        context_parts.append(
            f"[Source {i}] {title}\n"
            f"URL: {url}\n"
            f"Content: {content}\n"
        )
        
        sources.append({
            "index": i,
            "title": title,
            "url": url,
        })
    
    context_text = "\n---\n".join(context_parts)
    
    return context_text, sources
