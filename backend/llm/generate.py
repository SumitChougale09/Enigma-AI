"""
LLM Generation via Groq
───────────────────────
Two modes:
  1. generate_answer()        → blocking, returns full string
  2. generate_answer_stream() → yields token-by-token (for SSE/frontend)

Production pattern: Model fallback chain
  - If one Groq model is unavailable or rate-limited, try the next
  - This keeps the streaming/blocking pipeline unchanged while swapping providers
"""

import os
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from typing import Generator

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("Missing GROQ_API_KEY in environment or .env file")

# Groq is OpenAI-compatible, so the existing OpenAI SDK integration still works.
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=GROQ_API_KEY,
)

# Load the prompt template once
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "answer_prompt.txt"
PROMPT_TEMPLATE = PROMPT_PATH.read_text()

# Model fallback chain — if one model is rate-limited, try the next.
MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
]
DEFAULT_MODEL = MODELS[0]


def _build_messages(query: str, context: str, history: list[dict] | None = None) -> tuple[list[dict], str]:
    """
    Build the chat messages array from query + context.
    Shared between streaming and non-streaming modes.
    """
    current_date = datetime.now().strftime("%B %d, %Y")
    prompt = PROMPT_TEMPLATE.format(context=context, query=query, date=current_date)

    messages = [
        {
            "role": "system",
            "content": (
                f"You are a real-time AI research assistant. Today is {current_date}. "
                "CRITICAL: Answer ONLY from the web search results provided in the user message. "
                "Your training data is outdated for real-time facts — sports, news, prices, rankings. "
                "NEVER use your parametric memory for real-time information. "
                "If the search results don't contain the answer, say so explicitly."
            )
        }
    ]

    # Inject raw chat memory
    if history:
        messages.extend(history)

    # Append current query + context
    messages.append({
        "role": "user",
        "content": prompt
    })

    # Visualize/log memory usage
    print("\n" + "="*50)
    print(f"🧠 MEMORY USAGE VISUALIZATION ({len(messages)} messages total)")
    print("="*50)
    for i, m in enumerate(messages):
        preview = m['content'].replace("\n", " ")[:100]
        print(f"[{i}] {m['role'].upper()}: {preview}...")
    print("="*50 + "\n")

    return messages, current_date


def generate_answer(query: str, context: str, model: str | None = None, history: list[dict] | None = None) -> str:
    """
    Blocking call — returns the full answer as a string.
    Tries fallback models if the primary is rate-limited.
    """
    messages, _ = _build_messages(query, context, history=history)
    models_to_try = [model] if model else MODELS

    last_error = None
    for m in models_to_try:
        try:
            response = client.chat.completions.create(
                model=m,
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            if "429" in str(e) or "rate" in str(e).lower():
                continue  # Try next model
            raise  # Non-rate-limit error, raise immediately

    raise last_error  # All models exhausted


def generate_answer_stream(
    query: str, context: str, model: str | None = None, history: list[dict] | None = None
) -> Generator[str, None, None]:
    """
    Streaming call — yields tokens one-by-one as the LLM generates them.
    Tries fallback models if the primary is rate-limited.
    
    How it works under the hood:
      1. We send stream=True to the OpenAI SDK
      2. The SDK returns an iterator of ChatCompletionChunk objects
      3. Each chunk has a .choices[0].delta.content field (a small text fragment)
      4. We yield each fragment as it arrives — no waiting for the full response
      5. The caller (FastAPI SSE or CLI) decides how to format/send each token
    """
    messages, _ = _build_messages(query, context, history=history)
    models_to_try = [model] if model else MODELS

    last_error = None
    for m in models_to_try:
        try:
            stream = client.chat.completions.create(
                model=m,
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            return  # Successfully completed streaming

        except Exception as e:
            last_error = e
            if "429" in str(e) or "rate" in str(e).lower():
                continue  # Try next model
            raise

    raise last_error
