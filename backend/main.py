"""
ARIA — FastAPI Server + CLI
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
import uuid
import asyncio
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from sqlalchemy.orm import Session

from tools.search import search_web
from core.context_builder import build_context
from core.formatter import format_response_with_citations
from llm.generate import generate_answer, generate_answer_stream
from routes import router as app_router
from db import get_db, get_session_factory
from models import Chat, Message, Profile
from auth import get_current_user_claims, get_or_create_profile
from chat_service import (
    add_message,
    create_chat,
    get_chat_by_id,
    get_user_chat,
    get_chat_history_as_messages,
    list_chat_messages,
    delete_chat,
)

# ─── FastAPI App ──────────────────────────────────────────────

app = FastAPI(
    title="ARIA",
    description="AI-powered search assistant with citations — streaming & blocking modes",
    version="0.3.0",
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
    chat_id: str | None = None  # If provided, fetches history from DB


class SearchResponse(BaseModel):
    query: str
    search_query: str | None = None
    answer: str
    citations: str
    sources: list[dict]
    chat_id: str | None = None


# ─── Shared Pipeline Steps ────────────────────────────────────

def reformulate_query(query: str, history: list[dict] | None = None) -> str:
    """
    Use the LLM to rewrite vague follow-up queries using chat history.
    e.g. "How old is he?" + history about Tim Cook → "How old is Tim Cook?"
    
    This is how Perplexity resolves pronouns and references in follow-up questions.
    If there's no history, returns the original query unchanged.
    """
    if not history:
        print(f"\n🔍 SEARCH QUERY (no history, using original): \"{query}\"")
        return query

    from openai import OpenAI
    import os
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.getenv("GROQ_API_KEY"),
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a query reformulation engine. Given a chat history and a follow-up question, "
                "rewrite the follow-up question to be a STANDALONE search query that includes all "
                "necessary context. Replace all pronouns and references with their actual values.\n\n"
                "Rules:\n"
                "- Output ONLY the rewritten query, nothing else\n"
                "- Keep it concise (search-engine friendly)\n"
                "- If the query is already standalone, return it as-is\n\n"
                "Example:\n"
                "History: User asked 'Who is the CEO of Apple?' → Assistant said 'Tim Cook'\n"
                "Follow-up: 'How old is he?'\n"
                "Output: 'How old is Tim Cook?'"
            )
        }
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": f"Rewrite this as a standalone search query: {query}"})

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Fast small model for reformulation
            messages=messages,
            temperature=0.0,
            max_tokens=100,
        )
        reformulated = response.choices[0].message.content.strip().strip('"\'')
        print(f"\n🔄 QUERY REFORMULATION:")
        print(f"   Original:     \"{query}\"")
        print(f"   Reformulated: \"{reformulated}\"")
        print(f"   History msgs: {len(history)}")
        return reformulated
    except Exception as e:
        print(f"\n⚠️ Query reformulation failed ({e}), using original query")
        return query


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


def _get_or_create_chat(db: Session, chat_id: str | None) -> Chat:
    """
    If chat_id is provided, fetch it from DB.
    If not, create a new anonymous chat for testing.
    """
    if chat_id:
        chat = get_chat_by_id(db, uuid.UUID(chat_id))
        if not chat:
            raise HTTPException(status_code=404, detail=f"Chat {chat_id} not found")
        print(f"\n💬 USING EXISTING CHAT: {chat.id} (title: {chat.title})")
        return chat
    else:
        # Auto-create anonymous chat
        anon_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        profile = db.get(Profile, anon_id)
        if not profile:
            profile = Profile(id=anon_id, email="anonymous@test.local")
            db.add(profile)
            db.commit()
            db.refresh(profile)
        chat = Chat(user_id=anon_id, title="New chat")
        db.add(chat)
        db.commit()
        db.refresh(chat)
        print(f"\n💬 CREATED NEW CHAT: {chat.id}")
        return chat


def run_pipeline(query: str, max_results: int = 5, chat_id: str | None = None) -> dict:
    """
    Full blocking pipeline: search → context → LLM → citations.
    Now uses chat_id to fetch/save history from the database.
    """
    # Get a DB session
    session_factory = get_session_factory()
    db = session_factory()

    try:
        # Step 0: Get or create chat
        chat = _get_or_create_chat(db, chat_id)
        resolved_chat_id = str(chat.id)

        # Step 1: Fetch history from DB
        history = get_chat_history_as_messages(db, chat.id)

        # Step 2: Reformulate query using DB history
        search_query = reformulate_query(query, history if history else None)

        # Step 3: Search + Context
        context_text, sources = run_search_and_context(search_query, max_results)

        # Step 4: Generate answer
        raw_answer = generate_answer(
            query=query, context=context_text,
            history=history if history else None,
        )

        # Step 5: Save user message + assistant response to DB
        add_message(db, chat=chat, user_id=None, role="user", content=query)
        add_message(db, chat=chat, user_id=None, role="assistant", content=raw_answer)
        print(f"\n💾 SAVED 2 messages to chat {resolved_chat_id}")

        # Step 6: Format response
        response = format_response_with_citations(raw_answer, sources)
        response["query"] = query
        response["search_query"] = search_query
        response["chat_id"] = resolved_chat_id
        return response
    finally:
        db.close()



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


# ─── Streaming API Endpoint (SSE) — Authenticated ────────────

@app.post("/stream")
async def stream_endpoint(
    request: SearchRequest,
    authorization: str | None = Header(default=None),
):
    """
    POST /stream — Server-Sent Events streaming endpoint.
    
    Supports both authenticated (with Bearer token) and anonymous modes.
    When authenticated, uses the user's chat and saves messages.
    When anonymous (no token), creates a temporary chat.
    
    The frontend sends the auth token + chat_id, and the backend handles
    ALL message persistence. The frontend should NOT separately call
    POST /chats/{id}/messages — that would cause duplication.
    """
    # Try to resolve the authenticated user (optional)
    user_id = None
    if authorization:
        try:
            claims = await get_current_user_claims(authorization)
            user_id = uuid.UUID(claims["sub"])
        except HTTPException:
            pass  # Fall through to anonymous mode

    async def event_stream():
        session_factory = get_session_factory()
        db = session_factory()

        try:
            # Phase 0: Get or create chat
            if request.chat_id:
                chat = get_chat_by_id(db, uuid.UUID(request.chat_id))
                if not chat:
                    yield sse_event("error", {
                        "type": "error",
                        "message": f"Chat {request.chat_id} not found",
                    })
                    return
                # Verify ownership if authenticated
                if user_id and chat.user_id != user_id:
                    yield sse_event("error", {
                        "type": "error",
                        "message": "You do not own this chat",
                    })
                    return
            else:
                # No chat_id provided — create a new one
                if user_id:
                    profile = db.get(Profile, user_id)
                    if not profile:
                        yield sse_event("error", {
                            "type": "error",
                            "message": "Profile not found",
                        })
                        return
                    chat = Chat(user_id=user_id, title=request.query[:80])
                    db.add(chat)
                    db.commit()
                    db.refresh(chat)
                else:
                    chat = _get_or_create_chat(db, None)

            resolved_chat_id = str(chat.id)

            # Fetch history from DB
            history = get_chat_history_as_messages(db, chat.id)

            # Reformulate query using DB history
            search_query = reformulate_query(
                request.query, history if history else None
            )

            # Phase 1: Status update — searching
            yield sse_event("status", {
                "type": "status",
                "message": f"Searching the web for: {search_query}",
                "step": 1,
                "search_query": search_query,
                "chat_id": resolved_chat_id,
            })

            # Phase 2: Run search + context building (using reformulated query)
            context_text, sources = run_search_and_context(
                search_query, request.max_results
            )

            # Phase 3: Send sources immediately
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
                query=request.query, context=context_text,
                history=history if history else None,
            ):
                full_answer += token
                yield sse_event("token", {
                    "type": "token",
                    "content": token,
                })

            # Phase 6: Save BOTH messages to DB (backend handles ALL persistence)
            add_message(db, chat=chat, user_id=user_id, role="user", content=request.query)
            add_message(db, chat=chat, user_id=user_id, role="assistant", content=full_answer.strip())
            print(f"\n💾 SAVED 2 messages to chat {resolved_chat_id}")

            # Phase 7: Done — include chat_id so frontend can track it
            yield sse_event("done", {
                "type": "done",
                "query": request.query,
                "full_answer": full_answer.strip(),
                "chat_id": resolved_chat_id,
            })

        except Exception as e:
            print(f"\n❌ STREAM ERROR: {e}")
            yield sse_event("error", {
                "type": "error",
                "message": str(e),
            })
        finally:
            db.close()

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

@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """
    POST /search — Non-streaming endpoint.
    Returns the complete answer at once.
    Now uses chat_id for DB-backed conversation history.
    """
    result = run_pipeline(request.query, request.max_results, chat_id=request.chat_id)
    return result


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aria", "version": "0.3.0"}


# ─── Delete Chat ──────────────────────────────────────────────

@app.delete("/chats/{chat_id}")
async def delete_chat_endpoint(
    chat_id: str,
    claims=Depends(get_current_user_claims),
    db: Session = Depends(get_db),
):
    """Delete a chat (authenticated). Only the owner can delete."""
    profile = get_or_create_profile(db, claims)
    chat = get_user_chat(db, profile.id, uuid.UUID(chat_id))
    delete_chat(db, chat)
    return {"status": "deleted", "chat_id": chat_id}


# ─── Rename Chat ─────────────────────────────────────────────

class RenameChatRequest(BaseModel):
    title: str

@app.patch("/chats/{chat_id}")
async def rename_chat_endpoint(
    chat_id: str,
    request: RenameChatRequest,
    claims=Depends(get_current_user_claims),
    db: Session = Depends(get_db),
):
    """Rename a chat (authenticated). Only the owner can rename."""
    profile = get_or_create_profile(db, claims)
    chat = get_user_chat(db, profile.id, uuid.UUID(chat_id))
    chat.title = request.title
    db.commit()
    db.refresh(chat)
    return {"status": "renamed", "chat_id": chat_id, "title": chat.title}


# ─── Test Endpoints (no auth, Postman-friendly) ──────────────

@app.post("/test/chat")
async def create_test_chat():
    """
    Create an anonymous chat for Postman testing.
    No auth required. Returns a chat_id you can use in /search and /stream.
    """
    session_factory = get_session_factory()
    db = session_factory()
    try:
        anon_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        profile = db.get(Profile, anon_id)
        if not profile:
            profile = Profile(id=anon_id, email="anonymous@test.local")
            db.add(profile)
            db.commit()
            db.refresh(profile)

        chat = Chat(user_id=anon_id, title="New chat")
        db.add(chat)
        db.commit()
        db.refresh(chat)
        print(f"\n🧪 TEST: Created chat {chat.id}")
        return {
            "chat_id": str(chat.id),
            "title": chat.title,
            "message": "Use this chat_id in /search or /stream requests",
        }
    finally:
        db.close()


@app.get("/test/chat/{chat_id}/history")
async def get_test_chat_history(chat_id: str):
    """
    View all messages stored in a chat — for debugging.
    """
    session_factory = get_session_factory()
    db = session_factory()
    try:
        history = get_chat_history_as_messages(db, uuid.UUID(chat_id))
        return {
            "chat_id": chat_id,
            "message_count": len(history),
            "messages": history,
        }
    finally:
        db.close()


# ─── CLI Mode (Streaming) ────────────────────────────────────

def run_cli():
    """
    Interactive terminal mode with real-time token streaming.
    Tokens appear one-by-one as the LLM generates them — same UX as ChatGPT.
    """
    console = Console()

    console.print(
        Panel(
            "[bold cyan]🔍 ARIA[/bold cyan]\n"
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
