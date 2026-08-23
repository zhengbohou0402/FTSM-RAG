# FTSM-RAG

A **Retrieval-Augmented Generation (RAG)** assistant for UKM FTSM student information, built with FastAPI and LangChain. It answers questions about FTSM and UKM student life by retrieving from a local knowledge base and generating grounded responses with a Tongyi / DashScope chat model.

> This is the original Python implementation. The Java migration lives in [`FTSM-RAG-Java`](https://github.com/zhengbohou0402/FTSM-RAG-Java); the multi-agent CloudOps variant is [`RAG-Python-MultiAgent`](https://github.com/zhengbohou0402/RAG-Python-MultiAgent).

## Key Features

- **Three-stage retrieval** — multi-query vector search (Qdrant) + BM25 keyword search, fused with Reciprocal Rank Fusion (RRF), then re-ranked by DashScope `gte-rerank-v2`.
- **Semantic cache** — cosine-similarity cache (threshold 0.92) that avoids redundant LLM calls and tracks hit/miss rate at runtime.
- **LangChain ReAct agent** — tools include `rag_summarize` (retrieval + answer) with a web-search fallback.
- **Streaming responses** — SSE-based character streaming (no WebSocket complexity).
- **Collapsible source cards** — every answer cites sources with file name, chunk index, excerpt, and a source-credibility label.
- **Backend conversation history** — per-file JSON under `data/ukm_ftsm/conversations/`, with a unified DELETE API (incl. "Clear All").
- **Indexing status polling** — upload → auto-index; the management page shows live running / pending / success / error.
- **Knowledge-base & cache stats** — `/api/knowledge/stats` and `/api/cache/stats` aggregate doc/chunk counts, index version, source-type distribution, and cache hit rate.
- **RAG evaluation suite** — MRR, Precision@K, Recall@K, Latency P50/P90; export to JSON / Markdown / CSV.
- **Encoding health check** — scans KB and source text before indexing to catch mojibake early.
- **System dashboard** — `/dashboard` aggregates all runtime metrics on one page.
- **Desktop app** — packaged as a Windows EXE via PyInstaller + Edge WebView2 (no browser required).
- **Crawler disabled in EXE** — the dev-only Playwright crawler is skipped automatically when running as a packaged executable.

## Project Layout

```text
.
├── launcher.py              # EXE entry point (PyInstaller)
├── ftsm_rag.spec            # PyInstaller spec (onedir)
├── web_app.py               # FastAPI application + all API routes
├── agent/                   # LangChain ReAct agent and tool definitions
├── rag/
│   ├── rag_service.py       # BM25 + Vector + RRF + Reranker pipeline
│   ├── vector_store.py      # Qdrant wrapper, incremental indexing
│   └── ingestion.py         # Document loading, chunking, manifest
├── model/                   # Chat and embedding model factories
├── config/                  # YAML config (rag.yml, qdrant.yml, scheduler.yml)
├── prompts/                 # System and RAG prompt templates
├── scripts/
│   ├── scrape_ftsm_website.py   # FTSM website crawler (dev-only, not bundled)
│   ├── evaluate_rag.py          # RAG evaluation: MRR, P@K, R@K, Latency
│   └── evaluate_cache.py        # Semantic cache latency and hit-rate experiment
├── services/                # Thin service layer (chat, documents, settings)
├── utils/                   # Config, scheduler, semantic cache, conversation store
├── web/                     # Static frontend (HTML/CSS/JS) + Jinja2 templates
├── data/ukm_ftsm/
│   ├── conversations/       # Per-file conversation JSON + index.json
│   └── semantic_cache.json  # Persisted semantic cache
└── qdrant_db_ftsm/          # Qdrant vector store (shipped with the release)
```

## Runtime Stack

| Component | Implementation |
| --- | --- |
| Web backend | FastAPI + Uvicorn |
| Frontend | Static HTML/CSS/JS (SSE streaming, no framework) |
| Agent framework | LangChain ReAct (`create_react_agent`) |
| Retrieval | Qdrant (vector) + BM25 → RRF → DashScope `gte-rerank-v2` |
| Chat model | DashScope Tongyi (default `qwen3-max`, switchable in UI) |
| Embedding model | DashScope `text-embedding-v3` |
| Vector store | Qdrant via `langchain-qdrant` |
| Semantic cache | Cosine similarity cache, persisted to JSON |
| Conversation storage | Per-file JSON directory (no database required) |
| Image text extraction | DashScope Qwen-VL + Pillow |
| Scheduled crawling | Playwright (dev-only; auto-disabled in packaged EXE) |

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/config/status` | Whether a DashScope API key is set |
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
| POST | `/api/knowledge/update` | Manually crawl the FTSM website and rebuild the index |
| GET | `/api/cache/stats` | Cache hit count, miss count, hit rate |
| GET | `/api/scheduler/status` | Crawler scheduler state |

## Development (running from source)

**Requirements:** Python 3.12, a DashScope API key.

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

The management page includes an **Update from FTSM site** button. Source builds use Playwright when Chromium is installed; packaged EXE builds use a lightweight HTTP/BeautifulSoup fallback so the button can still refresh `data/ukm_ftsm/ftsm_official_website.txt` and rebuild Qdrant without bundling Chromium. Scheduled crawling is disabled by default in `config/scheduler.yml`. Crawler seed URLs and allowed URL prefixes are configured in `config/crawler.yml`.

Open <http://127.0.0.1:8000/>. If no API key is set, you are redirected to `/settings` automatically.

## RAG Evaluation

```powershell
# Retrieval-only (fast)
python scripts/evaluate_rag.py

# Retrieval-only with JSON / Markdown / CSV report files
python scripts/evaluate_rag.py --report-dir results/rag_eval

# Full evaluation with LLM answers + JSON / Markdown / CSV report files
python scripts/evaluate_rag.py --with-answer --report-dir results/rag_eval_answer
```

Metrics reported: Source Hit Rate, first-hit rank, MRR, Precision@5, Recall@5, Answer Hit Rate, source coverage, failed cases, and Latency P50/P90.

## Checking Text Encoding

```powershell
python scripts/encoding_health.py --json results/encoding_health.json --fail-on-warning
```

This scans the knowledge base and project text files for common mojibake markers before documents are indexed into Qdrant.

## Cache Experiment

```powershell
python scripts/evaluate_cache.py --report-dir results/cache_eval
```

Produces JSON, Markdown, and CSV reports comparing no-cache answer latency, exact cache reuse, near-duplicate question reuse, cache hit rate, and similarity scores. Uses an in-memory cache; does not clear the app's persisted `semantic_cache.json`.

## Packaging

- **Windows installer:** `python scripts/build_windows_installer.py` → `dist/FTSM-RAG-0.1.1-windows-x64-setup.exe`.
- **Portable ZIP:** `pyinstaller ftsm_rag.spec` then `python scripts/build_release_zip.py` → `dist/FTSM-RAG/` and `dist/FTSM-RAG-windows.zip`.

Packaged EXE differences: scheduled Playwright crawler is auto-disabled; Qdrant + KB files are copied next to the EXE on first run; Edge WebView2 runtime required (force browser mode with `FTSM_BROWSER_MODE=1`).

## Adding Documents

1. Open `/manage` → drag & drop files → indexing starts automatically, **or**
2. Place files into `data/ukm_ftsm/` and run `python rag/vector_store.py` from source.

Supported: TXT, PDF, PNG, JPG, JPEG, WEBP, GIF (max 50 MB each).

## Settings UI (`/settings`)

- **API Key** — saved to `.env`; displayed masked (`sk-****xxxx`); only overwritten when a new key is entered.
- **Service Region** — China (`dashscope.aliyuncs.com`) or International (`dashscope-intl.aliyuncs.com`).
- **Chat Model** — `qwen3-max`, `qwen-plus`, `qwen-turbo`, `qwen3.6-plus`, etc.

Changes apply immediately without restart.

## Ignored Local Files

`.venv/`, `logs/`, `dist/`, `build/`, `.env`, `data/ukm_ftsm/conversations/`, `data/ukm_ftsm/semantic_cache.json`, `data/ukm_ftsm/.last_crawl` are git-ignored.
