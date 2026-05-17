"""
Citation Formatter
──────────────────
Formats the final LLM response with proper source citations,
both for terminal (Rich) and API (JSON) output.

Learning point: Good citation formatting is what makes an AI search
assistant trustworthy — users need to verify claims against sources.
"""


def format_response_with_citations(answer: str, sources: list[dict]) -> dict:
    """
    Take the raw LLM answer and source list, return a structured response
    with the answer and a formatted citation block.
    
    Args:
        answer: Raw text from the LLM
        sources: List of {index, title, url} dicts
        
    Returns:
        dict with 'answer', 'citations', and 'sources_used'
    """
    # Build citation footer
    citation_lines = []
    for src in sources:
        citation_lines.append(
            f"[{src['index']}] {src['title']}\n    {src['url']}"
        )
    
    citations_block = "\n".join(citation_lines)
    
    return {
        "answer": answer.strip(),
        "citations": citations_block,
        "sources": sources,
    }
