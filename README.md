# SyncLayer

> Cross-team intelligence for engineering organizations. Built for the
> Bending Spoons challenge at HackUPC 2026.

SyncLayer ingests **meetings**, **GitHub repos**, **Slack channels**, and
**project tickets** from every team in a company, builds a semantic map of
all ongoing work, and detects **conflicts**, **duplications**, and
**hidden dependencies** before they become production problems.

## Pipeline

```
sources ─► extractors ─► embeddings ─► FAISS ─► normalizer (Claude)
                                                       │
                                                       ▼
                                       conflict classification ─► graph + dashboard
```

| Step | Module | What it does |
|------|--------|--------------|
| 1 | `backend/extractors/*` | Claude pulls structured entities from each source |
| 2 | `backend/semantic/embeddings.py` | sentence-transformers + FAISS cosine index |
| 3 | `backend/semantic/embeddings.py::find_cross_team_matches` | top-k cross-team matches above threshold |
| 4 | `backend/semantic/normalizer.py` | Claude tags each pair as `same_concept`, `conflicting`, `dependent`, or `unrelated` |
| 5 | `backend/detection/conflict.py` | Maps normalized pairs to `DUPLICATION`, `CONTRADICTION`, `HIDDEN_DEPENDENCY`, `SAY_VS_DO` with severities and recommendations |
| 6 | `backend/detection/graph.py` | NetworkX graph + interactive Pyvis HTML |

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # add your real API keys
```

Required: `ANTHROPIC_API_KEY`. Optional: `ASSEMBLYAI_API_KEY` (audio transcripts),
`GITHUB_TOKEN` (live repo sync), `SLACK_BOT_TOKEN` (live Slack sync).

## Run

```bash
# Standalone end-to-end demo (no servers)
python demo.py

# Or run the full stack
uvicorn backend.main:app --reload --port 8000      # backend
streamlit run frontend/app.py --server.port 8501   # dashboard (separate terminal)
```

The Streamlit dashboard works in two modes:
- **Local mode** (default): the pipeline runs in-process. No backend needed.
- **Backend mode**: toggle "Use FastAPI backend" in the sidebar to delegate
  ingestion and analysis to the FastAPI service.

## What the demo proves

The bundled data under `data/` is engineered to surface a realistic mix of
cross-team conflicts:

| # | Type | Description |
|---|------|-------------|
| 1 | DUPLICATION | Backend's JWT auth service vs Mobile's native login module |
| 2 | SAY_VS_DO | Backend says "keep REST" while the repo migrates to GraphQL |
| 3 | HIDDEN_DEPENDENCY | Infra deprecates legacy server while Mobile depends on it for payments |
| 4 | CONTRADICTION | Mobile builds a 5-step onboarding while Infra enforces a 3-step max |
| 5 | DUPLICATION | Three teams independently solve duplicate notifications |
| 6 | HIDDEN_DEPENDENCY | Mobile bypasses the auth gateway that Infra mandates |

## API

Selected endpoints exposed by `backend/main.py`:

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/` | Health check |
| `POST` | `/ingest/meeting` | Form-data: `team`, optional `transcript_text` or `audio` file |
| `POST` | `/ingest/repo` | JSON: `team` + `repo_full_name` or `json_path` |
| `POST` | `/ingest/slack` | JSON: `team` + `channel_id` or `json_path` |
| `POST` | `/ingest/tickets` | Multipart: `team` + JSON `file` |
| `POST` | `/sync/github/{owner}/{repo}?team=…` | Live PyGithub fetch |
| `POST` | `/sync/slack/{channel_id}?team=…` | Live Slack fetch |
| `POST` | `/analyze` | Run the full pipeline against current state |
| `GET`  | `/entities` `/conflicts` `/events` `/graph` `/graph/html` `/report` | Read endpoints |
| `POST` | `/reset` | Clear in-memory state |

## Notes & decisions

- All Claude calls use `temperature=0` and we strip markdown fencing before
  parsing JSON — see `backend/extractors/_claude.py`.
- Embeddings are L2-normalized so a `IndexFlatIP` becomes cosine similarity.
- The default FAISS threshold is `0.45`. Lower for recall, higher for precision.
- The normalizer batches pairs in groups of 10 (configurable via
  `NORMALIZER_BATCH_SIZE`).
- `all-MiniLM-L6-v2` is lazy-loaded on first use — first analysis takes a
  few seconds longer.
- For the live demo: ingest data and run analysis once **before** the
  presentation so embeddings + Claude calls are warm.

## Project layout

```
synclayer/
├── backend/
│   ├── main.py                  # FastAPI app
│   ├── config.py                # env-driven settings
│   ├── extractors/              # meeting · github · slack · tickets
│   ├── semantic/                # embeddings + Claude normalizer
│   ├── detection/               # conflict + graph
│   └── models/schemas.py        # Pydantic v2 models
├── frontend/app.py              # Streamlit dashboard
├── data/{meetings,repos,tickets,slack}/  # demo data
├── demo.py                      # standalone runner
└── requirements.txt
```
