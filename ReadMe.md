# FTSM-RAG

FTSM-RAG is a FastAPI-based **Retrieval-Augmented Generation (RAG)** assistant for UKM FTSM student information. It answers questions about FTSM and UKM student life by retrieving local knowledge-base documents and generating grounded responses with a Tongyi/DashScope chat model.

## Key Features

- **Three-stage retrieval pipeline** — Multi-query vector search (ChromaDB) + BM25 keyword search, fused with Reciprocal Rank Fusion (RRF), then re-ranked by DashScope `gte-rerank-v2`
- **Semantic cache** — Cosine-similarity cache (threshold 0.92) avoids redundant LLM calls; tracks hit/miss rate at runtime
- **LangChain ReAct agent** — Tools include `rag_summarize` (retrieval + answer) and a web-search fallback
- **Streaming responses** — SSE-based character streaming; no WebSocket complexity needed
- **Collapsible source cards** — Each answer shows cited sources with file name, chunk index, and excerpt
- **Conversation history (backend)** — Per-file JSON storage under `data/ukm_ftsm/conversations/`; unified DELETE API
- **Indexing status polling** — Upload → auto-index; management page shows live running / pending / success / error
- **Knowledge base stats** — `/api/knowledge/stats` returns doc count, chunk count, last indexed time, cache size
- **Cache stats** — `/api/cache/stats` returns hit count, miss count, hit rate; shown on management page
- **API key masking** — Settings page shows `sk-****xxxx`; only updated if user inputs a new key
- **RAG evaluation suite** — MRR, Precision@K, Recall@K, Latency P50/P90; export to JSON / Markdown / CSV
- **System dashboard** — `/dashboard` aggregates all runtime metrics in one page
- **Desktop app** — Bundled as a Windows EXE via PyInstaller + Edge WebView2 (no browser required)
- **Scheduled crawler disabled in EXE** — Dev-only Playwright crawler is automatically skipped when running as a packaged executable

## Project Layout

```text
.
├── launcher.py              # EXE entry point (PyInstaller)
├── ftsm_rag.spec            # PyInstaller spec (onedir)
├── web_app.py               # FastAPI application + all API routes
├── agent/                   # LangChain ReAct agent and tool definitions
├── rag/
│   ├── rag_service.py       # BM25 + Vector + RRF + Reranker pipeline
│   ├── vector_store.py      # ChromaDB wrapper, incremental indexing
│   └── ingestion.py         # Document loading, chunking, manifest
├── model/                   # Chat and embedding model factories
├── config/                  # YAML config (rag.yml, chroma.yml, scheduler.yml)
├── prompts/                 # System and RAG prompt templates
├── scripts/
│   ├── scrape_ftsm_website.py   # FTSM website crawler (dev-only, not bundled)
│   └── evaluate_rag.py          # RAG evaluation: MRR, P@K, R@K, Latency
├── services/                # Thin service layer (chat, documents, settings)
├── utils/                   # Config, scheduler, semantic cache, conversation store
├── web/                     # Static frontend (HTML/CSS/JS) + Jinja2 templates
├── data/ukm_ftsm/
│   ├── conversations/       # Per-file conversation JSON + index.json
│   └── semantic_cache.json  # Persisted semantic cache
└── chroma_db_ftsm/          # ChromaDB vector store (shipped with the release)
```

## Runtime Stack

| Component | Implementation |
| --- | --- |
| Web backend | FastAPI + Uvicorn |
| Frontend | Static HTML/CSS/JS (SSE streaming, no framework) |
| Agent framework | LangChain ReAct (`create_react_agent`) |
| Retrieval | ChromaDB (vector) + BM25 → RRF → DashScope `gte-rerank-v2` |
| Chat model | DashScope Tongyi (default `qwen3-max`, switchable in UI) |
| Embedding model | DashScope `text-embedding-v4` |
| Vector store | Chroma via `langchain-chroma` |
| Semantic cache | Cosine similarity cache, persisted to JSON |
| Conversation storage | Per-file JSON directory (no database required) |
| Image text extraction | DashScope Qwen-VL + Pillow |
| Scheduled crawling | Playwright (dev-only; auto-disabled in packaged EXE) |

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/config/status` | Whether DashScope API key is set |
| GET/POST | `/api/settings` | Read / save settings (key shown masked) |
| GET | `/api/models` | List available Qwen models + validate key |
| POST | `/api/chat` | Streaming chat (SSE) |
| GET/POST | `/api/conversations` | List / create conversations |
| GET | `/api/conversations/{id}` | Get conversation with messages |
| DELETE | `/api/conversations/{id}` | Delete a conversation |
| GET/POST | `/api/documents` | List / upload knowledge-base files |
| DELETE | `/api/documents/{filename}` | Delete a document + its vector chunks |
| GET/POST | `/api/training/status` `/api/training/start` | Indexing status and trigger |
| GET | `/api/knowledge/stats` | Doc count, chunk count, last indexed time, cache size |
| GET | `/api/cache/stats` | Cache hit count, miss count, hit rate |
| GET | `/api/scheduler/status` | Crawler scheduler state |

## Development (running from source)

**Requirements:** Python 3.12, a DashScope API key

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Optional: install Chromium for the crawler
python -m playwright install chromium

# Create your env file (or fill via the /settings UI on first run)
Copy-Item .env.example .env
# Edit .env: set DASHSCOPE_API_KEY=sk-...

uvicorn web_app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/>. If no API key is set, you are redirected to `/settings` automatically.

## Running the RAG Evaluation

```powershell
# Retrieval-only (fast)
python scripts/evaluate_rag.py

# Full evaluation with LLM answers + all exports
python scripts/evaluate_rag.py --with-answer \
    --output results/rag_eval.json \
    --markdown results/rag_eval.md \
    --csv results/rag_eval.csv
```

Metrics reported: Source Hit Rate, MRR, Precision@5, Recall@5, Latency P50/P90.

## Packaging as a Standalone EXE (Windows)

```powershell
# From the activated .venv
pyinstaller ftsm_rag.spec
```

Output: `dist/FTSM-RAG/` — zip the entire folder and distribute. Users double-click `FTSM-RAG.exe`; the app opens in a dedicated desktop window. On first run the settings page loads for API key input.

**Packaged EXE differences from source:**
- Scheduled Playwright crawler is **automatically disabled** (Playwright not bundled)
- ChromaDB vector store and knowledge-base files are copied next to the EXE on first run
- Edge WebView2 runtime required (pre-installed on Windows 11 / recent Windows 10)

If WebView2 is unavailable, the EXE falls back to the default browser. Force browser mode: set `FTSM_BROWSER_MODE=1`.

## Adding Documents

1. Open `/manage` in the browser → drag & drop files → indexing starts automatically
2. Or place files into `data/ukm_ftsm/` and run `python rag/vector_store.py` from source

Supported: TXT, PDF, PNG, JPG, JPEG, WEBP, GIF (max 50 MB each).

## Settings UI (`/settings`)

- **API Key** — saved to `.env`; displayed masked (`sk-****xxxx`); only overwritten when you enter a new key
- **Service Region** — China (`dashscope.aliyuncs.com`) or International (`dashscope-intl.aliyuncs.com`)
- **Chat Model** — pick from `qwen3-max`, `qwen-plus`, `qwen-turbo`, `qwen3.6-plus`, etc.

Changes apply immediately without restart.

## System Dashboard (`/dashboard`)

Real-time view of:
- Knowledge base statistics (documents, indexed chunks, last indexed)
- Semantic cache performance (hit rate, hit/miss counts, valid entries)
- Indexing worker status (running / idle / last result)
- Scheduler status (next crawl time)

## Ignored Local Files

Generated at runtime, excluded from git:

- `.venv/`
- `logs/`, `dist/`, `build/`
- `.env`
- `data/ukm_ftsm/conversations/`
- `data/ukm_ftsm/semantic_cache.json`
- `data/ukm_ftsm/.last_crawl`
