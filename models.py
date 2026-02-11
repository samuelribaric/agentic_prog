"""Ollama model wrappers — one for tool-calling, one for reasoning."""

import re

from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage

import config


def get_tool_model() -> ChatOllama:
    """Return the tool-calling model (llama3.1:8b)."""
    return ChatOllama(
        model=config.TOOL_MODEL,
        base_url=config.OLLAMA_BASE_URL,
        temperature=0,
    )


def get_reasoning_model() -> ChatOllama:
    """Return the reasoning model (deepseek-r1:8b)."""
    return ChatOllama(
        model=config.REASONING_MODEL,
        base_url=config.OLLAMA_BASE_URL,
        temperature=0.1,
    )


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from DeepSeek output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def clean_reasoning_response(message: AIMessage) -> AIMessage:
    """Return a copy of the message with think tags stripped."""
    cleaned = strip_think_tags(message.content)
    return AIMessage(content=cleaned)
