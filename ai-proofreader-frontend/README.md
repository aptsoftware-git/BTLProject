# AI Proofreader — frontend

A React + Vite dashboard matching the target design (purple/indigo brand
color, 4 stat tiles, drag-and-drop upload, recent documents list).

## 1. Run the frontend

```bash
cd ai-proofreader-frontend
npm install
npm run dev
```

Opens at http://localhost:5173. It will run fine on its own — the stat
cards and document list just show empty/zero data until the backend
responds (see the yellow banner if that happens).

## 2. What it expects from your backend

Your `backend/` folder (app.py, routes.py, schemas.py, services.py) needs
to expose these endpoints. Adjust the paths in `src/api.js` if your
`routes.py` names them differently — that's the only file that needs to
change to match your actual API.

| Method | Path                  | Returns                                                                                  |
|--------|------------------------|-------------------------------------------------------------------------------------------|
| GET    | `/api/stats`           | `{ "totalDocuments": 1, "grammarAccuracy": 86, "issuesResolvedToday": 0, "documentsToday": 0 }` |
| GET    | `/api/documents`       | `[{ "id": "1", "filename": "attention_is_all_you_need.pdf", "fileType": "PDF", "size": "4.2 MB", "uploadedLabel": "Uploaded just now", "status": "completed" }]` |
| GET    | `/api/system-status`   | `[{ "name": "Backend", "online": true }, ...]` (optional — sidebar falls back to a static list if this 404s) |
| POST   | `/api/documents`       | multipart form with a `file` field; kicks off the proofreading job and returns the created document |
| GET    | `/api/documents/:id`   | full result for a single document (for the future workspace/editor page) |

`status` should be one of `"completed"`, `"processing"`, or `"failed"` —
the UI colors the pill accordingly.

## 3. Wiring it up (FastAPI example, since your files look like FastAPI)

In `app.py`, enable CORS so the browser (localhost:5173) is allowed to
call the API (localhost:8000) during development:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

In `routes.py`, make sure the routes above exist and return JSON shaped
like the tables. A minimal example for the documents list:

```python
@router.get("/documents")
def list_documents():
    docs = services.get_recent_documents()  # your existing logic
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "fileType": d.filename.split(".")[-1].upper(),
            "size": f"{d.size_mb:.1f} MB",
            "uploadedLabel": services.humanize_time(d.uploaded_at),
            "status": d.status,  # "completed" | "processing" | "failed"
        }
        for d in docs
    ]
```

And for upload, in `routes.py`:

```python
@router.post("/documents")
async def upload_document(file: UploadFile = File(...)):
    result = await services.process_upload(file)
    return result
```

`schemas.py` is a good place to define these as Pydantic models
(`DocumentOut`, `StatsOut`, `SystemStatusOut`) so FastAPI validates and
documents the shapes automatically — the frontend doesn't care either
way, it just needs matching JSON keys.

## 4. Dev proxy (already set up)

`vite.config.js` proxies any request to `/api/*` from the frontend dev
server straight to `http://localhost:8000`, so you don't need CORS
enabled for local dev if you'd rather skip step 3's CORS snippet —
either approach works, the proxy is just more convenient day-to-day.
If your backend runs on a different port, change the `target` value in
`vite.config.js`.

## 5. Production

Set `VITE_API_BASE_URL` to your deployed backend's full URL (e.g.
`https://api.yourapp.com`) before running `npm run build`, since there's
no dev proxy once it's a static build:

```bash
VITE_API_BASE_URL=https://api.yourapp.com npm run build
```

## Project structure

```
src/
  api.js                  ← all fetch calls to the backend, edit paths here
  App.jsx                 ← page layout + data loading
  index.css               ← color tokens / design system
  components/
    Sidebar.jsx
    TopBar.jsx
    StatCard.jsx
    UploadZone.jsx
    RecentDocuments.jsx
```
