# Claude Copilot Web Console

Internal workspace UI for documents, research Q&A, metrics, and L3 eval reports.

## Run

```bash
# from repo root — API
uvicorn app.main:app --reload --port 8000

# from web/
npm install
npm run dev
```

Open http://localhost:5173 (Vite proxies `/api` and `/health` to port 8000).
