"""Centralized configuration loaded from environment variables."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# --- API keys ---------------------------------------------------------------
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")

# --- Models -----------------------------------------------------------------
# Default to Haiku for cost. Extraction is structured JSON — Haiku is plenty.
# Set CLAUDE_NORMALIZER_MODEL to a stronger model (e.g. claude-sonnet-4-5)
# if you want sharper reasoning on cross-source relationship classification.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
CLAUDE_EXTRACTION_MODEL = os.getenv("CLAUDE_EXTRACTION_MODEL", CLAUDE_MODEL)
CLAUDE_NORMALIZER_MODEL = os.getenv("CLAUDE_NORMALIZER_MODEL", CLAUDE_MODEL)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# --- Pipeline tuning --------------------------------------------------------
FAISS_THRESHOLD = float(os.getenv("FAISS_THRESHOLD", "0.45"))
NORMALIZER_BATCH_SIZE = int(os.getenv("NORMALIZER_BATCH_SIZE", "10"))

# --- Background poller ------------------------------------------------------
# How often the background poller re-syncs every configured repo. Floor
# enforced inside BackgroundPoller (10s). Set to 0 or negative to disable
# (the lifespan handler will skip starting it).
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# --- URLs -------------------------------------------------------------------
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
