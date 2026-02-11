"""Centralized config loader — reads from .env and exposes typed settings."""

import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
REASONING_MODEL: str = os.getenv("REASONING_MODEL", "deepseek-r1:8b")
TOOL_MODEL: str = os.getenv("TOOL_MODEL", "llama3.1:8b")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
MAX_SEARCH_ITERATIONS: int = int(os.getenv("MAX_SEARCH_ITERATIONS", "3"))
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
