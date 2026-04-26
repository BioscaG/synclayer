# SyncLayer · web

Editorial dashboard for SyncLayer. Talks to the FastAPI backend.

```bash
# 1) start the backend (root of the repo)
uvicorn backend.main:app --reload --port 8000

# 2) start the frontend (here)
cd web
npm install
npm run dev
# → http://localhost:3000
```

`next.config.ts` proxies `/api/*` to the FastAPI server (default `http://localhost:8000`).
Override with `BACKEND_URL=http://...` if you run the API elsewhere.

The Next.js dashboard includes a feature chat drawer wired to `POST /chat`.
It searches the backend's local project memory and shows the evidence used for
each answer.

The bundled Streamlit dashboard (`frontend/app.py`) still works as a fallback.
