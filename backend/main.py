"""
Mini Perplexity — FastAPI Server + CLI
───────────────────────────────────────
Three modes:
  1. CLI (streaming):  python main.py
  2. API (blocking):   POST /search
  3. API (streaming):  POST /stream  ← SSE for frontend consumption

SSE Protocol (what the frontend receives):
──────────────────────────────────────────
  event: status   → {"type": "status", "message": "Searching the web..."}
  event: sources  → {"type": "sources", "sources": [...], "citations": "..."}
  event: token    → {"type": "token", "content": "The"}
  event: done     → {"type": "done", "query": "...", "full_answer": "..."}
  event: error    → {"type": "error", "message": "Something went wrong"}

This is exactly how ChatGPT and Perplexity stream responses to their frontends.
"""

import sys
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live
from rich.text import Text

from tools.search import search_web
from core.context_builder import build_context
from core.formatter import format_response_with_citations
from llm.generate import generate_answer, generate_answer_stream
from routes import router as app_router

# ─── FastAPI App ──────────────────────────────────────────────

app = FastAPI(
    title="Mini Perplexity",
    description="AI-powered search assistant with citations — streaming & blocking modes",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(app_router)


# ─── Request / Response Models ────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    max_results: int = 5


class SearchResponse(BaseModel):
    query: str
    answer: str
    citations: str
    sources: list[dict]


# ─── Shared Pipeline Steps ────────────────────────────────────

def run_search_and_context(query: str, max_results: int = 5) -> tuple[str, list[dict]]:
    """
    Steps 1-2 of the pipeline: Search + Context Building.
    Shared between all modes (blocking API, streaming API, CLI).
    
    Returns:
        tuple of (context_text, sources)
    """
    search_results = search_web(query, max_results=max_results)
    context_text, sources = build_context(search_results)
    return context_text, sources


def run_pipeline(query: str, max_results: int = 5) -> dict:
    """
    Full blocking pipeline: search → context → LLM → citations.
    Used by the non-streaming /search endpoint.
    """
    context_text, sources = run_search_and_context(query, max_results)
    raw_answer = generate_answer(query=query, context=context_text)
    response = format_response_with_citations(raw_answer, sources)
    response["query"] = query
    return response


# ─── SSE Helper ───────────────────────────────────────────────

def sse_event(event_type: str, data: dict) -> str:
    """
    Format a single SSE (Server-Sent Events) message.
    
    SSE spec: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events
    
    Format:
        event: <type>\n
        data: <json>\n\n
    
    The double newline at the end is required by the SSE spec —
    it tells the browser "this event is complete, process it now."
    """
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ─── Streaming API Endpoint (SSE) ────────────────────────────

@app.post("/stream")
async def stream_endpoint(request: SearchRequest):
    """
    POST /stream — Server-Sent Events streaming endpoint.
    
    This is the endpoint your frontend will consume with EventSource or fetch().
    The response is a stream of typed events that the frontend processes in real-time.
    
    Frontend usage (JavaScript):
    
        const response = await fetch('/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: 'What is quantum computing?' })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const text = decoder.decode(value);
            // Parse SSE events from text...
        }
    """
    def event_stream():
        try:
            # Phase 1: Status update — searching
            yield sse_event("status", {
                "type": "status",
                "message": "Searching the web...",
                "step": 1,
            })

            # Phase 2: Run search + context building
            context_text, sources = run_search_and_context(
                request.query, request.max_results
            )

            # Phase 3: Send sources immediately — frontend can render these
            # while waiting for LLM tokens (this is what Perplexity does)
            citations = format_response_with_citations("", sources)
            yield sse_event("sources", {
                "type": "sources",
                "sources": sources,
                "citations": citations["citations"],
            })

            # Phase 4: Status update — generating
            yield sse_event("status", {
                "type": "status",
                "message": "Generating answer...",
                "step": 2,
            })

            # Phase 5: Stream LLM tokens one-by-one
            full_answer = ""
            for token in generate_answer_stream(
                query=request.query, context=context_text
            ):
                full_answer += token
                yield sse_event("token", {
                    "type": "token",
                    "content": token,
                })

            # Phase 6: Done — send the complete answer for frontend state management
            yield sse_event("done", {
                "type": "done",
                "query": request.query,
                "full_answer": full_answer.strip(),
            })

        except Exception as e:
            yield sse_event("error", {
                "type": "error",
                "message": str(e),
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if behind a proxy
        },
    )


# ─── Blocking API Endpoint (kept for backwards compatibility) ─

@app.post("/search", response_model=SearchResponse)
async def search_endpoint(request: SearchRequest):
    """
    POST /search — Non-streaming endpoint.
    Returns the complete answer at once.
    """
    result = run_pipeline(request.query, request.max_results)
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "service": "mini-perplexity", "version": "0.2.0"}


# ─── CLI Mode (Streaming) ────────────────────────────────────

def run_cli():
    """
    Interactive terminal mode with real-time token streaming.
    Tokens appear one-by-one as the LLM generates them — same UX as ChatGPT.
    """
    console = Console()

    console.print(
        Panel(
            "[bold cyan]🔍 Mini Perplexity[/bold cyan]\n"
            "[dim]AI-powered search assistant with streaming + citations[/dim]\n"
            "[dim]Type 'quit' to exit[/dim]",
            border_style="cyan",
        )
    )

    while True:
        console.print()
        query = console.input("[bold green]Ask anything → [/bold green]")

        if query.strip().lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye! 👋[/dim]")
            break

        if not query.strip():
            continue

        # Step 1: Search (with spinner)
        with console.status("[bold yellow]🔍 Searching the web...[/bold yellow]"):
            try:
                context_text, sources = run_search_and_context(query)
            except Exception as e:
                console.print(f"[bold red]Search Error:[/bold red] {e}")
                continue

        # Show sources immediately (like Perplexity does)
        if sources:
            source_text = "\n".join(
                f"  [cyan][{s['index']}][/cyan] {s['title']}"
                for s in sources
            )
            console.print(
                Panel(
                    source_text,
                    title="[bold yellow]📚 Sources Found[/bold yellow]",
                    border_style="yellow",
                    padding=(0, 1),
                )
            )

        # Step 2: Stream LLM answer token-by-token
        console.print()
        console.print("[bold cyan]Answer:[/bold cyan]")
        console.print("─" * 60)

        full_answer = ""
        try:
            for token in generate_answer_stream(query=query, context=context_text):
                full_answer += token
                # Print each token immediately without newline — creates typing effect
                console.print(token, end="", highlight=False)
        except Exception as e:
            console.print(f"\n[bold red]LLM Error:[/bold red] {e}")
            continue

        console.print()  # Final newline after streaming
        console.print("─" * 60)

        # Show formatted citations at the end
        if sources:
            citations = format_response_with_citations(full_answer, sources)
            console.print()
            console.print(
                Panel(
                    citations["citations"],
                    title="[bold yellow]📚 References[/bold yellow]",
                    border_style="yellow",
                    padding=(1, 2),
                )
            )


# ─── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    run_cli()
