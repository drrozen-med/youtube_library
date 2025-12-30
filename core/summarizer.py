"""
Summarizer
==========

LLM-based transcript summarization with auto-detection.

Features:
- Auto-detects Ollama (local) or OpenAI API
- Generates concise TL;DR summaries (3-5 bullets + key quote)
- Truncates long transcripts for efficiency
- Graceful fallback if no LLM available
"""

import os
from typing import Optional

from langchain_core.prompts import PromptTemplate


# Summarization prompt template
SUMMARY_PROMPT = PromptTemplate.from_template("""
You are an expert summarizer for YouTube educational content.
Given a transcript, produce a short TL;DR section that includes:
1. 3–5 bullet points summarizing key ideas.
2. 1 short quote or striking insight (if any).
3. Stay objective, concise, and factual.
Output only Markdown text, no preambles.

Transcript:
{text}

""")


def _try_ollama(snippet: str, model: str, verbose: bool) -> Optional[str]:
    """Try to use local Ollama model."""
    try:
        from langchain_community.llms import Ollama
        
        # Check if Ollama is running
        import subprocess
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            timeout=5
        )
        if result.returncode != 0:
            if verbose:
                print("⚠️  Ollama not running or not installed.")
            return None
        
        if verbose:
            print(f"🦙 Using local Ollama model: {model}")
        
        llm = Ollama(model=model)
        chain = SUMMARY_PROMPT | llm
        result = chain.invoke({"text": snippet})
        return getattr(result, "content", str(result)).strip()
    
    except ImportError:
        if verbose:
            print("⚠️  langchain-community not installed for Ollama support.")
        return None
    except Exception as e:
        if verbose:
            print(f"Ollama summarization failed: {e}")
        return None


def _try_openai(snippet: str, temperature: float, max_tokens: int, verbose: bool) -> Optional[str]:
    """Try to use OpenAI API."""
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        if verbose:
            print("⚠️  No OPENAI_API_KEY set.")
        return None
    
    try:
        from langchain_openai import ChatOpenAI
        
        if verbose:
            print("💬 Using OpenAI API for summarization.")
        
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=temperature,
            max_tokens=max_tokens
        )
        chain = SUMMARY_PROMPT | llm
        result = chain.invoke({"text": snippet})
        return getattr(result, "content", str(result)).strip()
    
    except ImportError:
        if verbose:
            print("⚠️  langchain-openai not installed.")
        return None
    except Exception as e:
        if verbose:
            print(f"OpenAI summarization failed: {e}")
        return None


def summarize_transcript(
    text: str,
    max_chars: int = 6000,
    max_tokens: int = 350,
    temperature: float = 0.2,
    verbose: bool = False,
) -> Optional[str]:
    """
    Summarize a transcript using either Ollama or OpenAI.
    
    Strategy:
    1. Try local Ollama first (if OLLAMA_MODEL set)
    2. Fall back to OpenAI API (if OPENAI_API_KEY set)
    3. Return None if neither available
    
    Args:
        text: Full transcript text
        max_chars: Truncate transcript to this length
        max_tokens: Max tokens for summary
        temperature: LLM temperature (0.0-1.0)
        verbose: Print status messages
    
    Returns:
        TL;DR markdown string or None
    """
    if not text or len(text.strip()) < 100:
        if verbose:
            print("⚠️  Transcript too short to summarize.")
        return None
    
    # Truncate very long transcripts
    snippet = text[:max_chars]
    
    # 1) Try local Ollama first
    ollama_model = os.getenv("OLLAMA_MODEL", "mistral")
    result = _try_ollama(snippet, ollama_model, verbose)
    if result:
        return result
    
    # 2) Try OpenAI API
    result = _try_openai(snippet, temperature, max_tokens, verbose)
    if result:
        return result
    
    if verbose:
        print("⚠️  No LLM backend found (set OPENAI_API_KEY or run Ollama).")
    
    return None
