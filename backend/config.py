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
SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET", "")
SLACK_REDIRECT_URI = os.getenv(
    "SLACK_REDIRECT_URI", "http://localhost:3000/api/slack/oauth/callback"
)
RECALL_API_KEY = os.getenv("RECALL_API_KEY", "")
RECALL_REGION = os.getenv("RECALL_REGION", "us-west-2")

# --- Models -----------------------------------------------------------------
# Default to Haiku for cost. Extraction is structured JSON — Haiku is plenty.
# Set CLAUDE_NORMALIZER_MODEL to a stronger model (e.g. claude-sonnet-4-5)
# if you want sharper reasoning on cross-source relationship classification.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
CLAUDE_EXTRACTION_MODEL = os.getenv("CLAUDE_EXTRACTION_MODEL", CLAUDE_MODEL)
CLAUDE_NORMALIZER_MODEL = os.getenv("CLAUDE_NORMALIZER_MODEL", CLAUDE_MODEL)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# --- Pipeline tuning --------------------------------------------------------
# Cosine-similarity floor for the cross-team matcher. Higher = less recall
# but stronger signal — we only want clear semantic overlap, not "same words
# vaguely related". 0.60 keeps only confident overlaps; drop to 0.55 for
# more recall.
FAISS_THRESHOLD = float(os.getenv("FAISS_THRESHOLD", "0.60"))
NORMALIZER_BATCH_SIZE = int(os.getenv("NORMALIZER_BATCH_SIZE", "10"))

# --- Background poller ------------------------------------------------------
# How often the background poller re-syncs every configured repo. Floor
# enforced inside BackgroundPoller (10s). Set to 0 or negative to disable
# (the lifespan handler will skip starting it).
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# --- URLs -------------------------------------------------------------------
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
